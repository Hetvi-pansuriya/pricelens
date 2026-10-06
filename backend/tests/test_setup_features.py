"""
tests/test_setup_features.py
Tests for setup wizard features:
- URL / Text import extraction and price verification
- CSV parsing (good file, bad rows, UTF-8 BOM, percent vs fraction)
- Stripe subscription grouping and unit conversion
- Company duplication
- Sample company creation
"""

import io
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

from main import app
from routers.setup import _verify_price_in_text, _parse_churn_rate
from routers.auth import get_current_user
from database import get_db
from models import User, Company, PricingTier, Feature


@pytest.fixture
def mock_user():
    return User(id=uuid.uuid4(), email="setup_tester@example.com")


@pytest.fixture
def client(mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_price_verification_in_text():
    sample_text = "Get our Pro plan for only $49/mo or $499 annually. Enterprise is $1,200/yr."
    
    assert _verify_price_in_text(49.0, sample_text) is True
    assert _verify_price_in_text(499.0, sample_text) is True
    assert _verify_price_in_text(1200.0, sample_text) is True
    assert _verify_price_in_text(None, sample_text) is True  # Custom pricing
    assert _verify_price_in_text(99.0, sample_text) is False  # Hallucinated price


def test_parse_churn_rate():
    assert _parse_churn_rate("0.05") == 0.05
    assert _parse_churn_rate("5%") == 0.05
    assert _parse_churn_rate("5") == 0.05  # > 1 interpreted as percent
    assert _parse_churn_rate("12.5%") == 0.125
    assert _parse_churn_rate("") is None
    assert _parse_churn_rate("   ") is None


def test_csv_parser_good_file(client):
    csv_content = (
        "\ufefftier_name,price,billing_cycle,user_count,churn_rate,features\r\n"
        "Starter,29,monthly,100,0.05,API Access;SSO\r\n"
        "Growth,79,annual,50,3%,Custom Workflows;Reports\r\n"
    ).encode("utf-8-sig")

    files = {"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}
    response = client.post("/setup/parse-csv", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert len(data["rows"]) == 2
    assert data["rows"][0]["name"] == "Starter"
    assert data["rows"][0]["price"] == 29.0
    assert data["rows"][0]["features"] == ["API Access", "SSO"]
    assert data["rows"][1]["billing_cycle"] == "annual"
    assert data["rows"][1]["churn_rate"] == 0.03


def test_csv_parser_currency_detection(client):
    csv_content = (
        "tier_name,price,billing_cycle,user_count,churn_rate\n"
        "Starter,₹499,monthly,100,5%\n"
        "Growth,₹1499,annual,50,3%\n"
    ).encode("utf-8")

    files = {"file": ("inr.csv", io.BytesIO(csv_content), "text/csv")}
    response = client.post("/setup/parse-csv", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data.get("detected_currency") == "INR"
    assert data["rows"][0]["price"] == 499.0
    assert data["rows"][1]["price"] == 1499.0


def test_csv_parser_bad_rows(client):
    csv_content = (
        "tier_name,price,billing_cycle,user_count,churn_rate,features\n"
        ",-10,unknown,-5,150%,Feature1\n"
    ).encode("utf-8")

    files = {"file": ("bad.csv", io.BytesIO(csv_content), "text/csv")}
    response = client.post("/setup/parse-csv", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0


def test_stripe_import_mocked(client):
    mock_active_sub = {
        "items": {
            "data": [
                {
                    "quantity": 1,
                    "price": {
                        "id": "price_123",
                        "unit_amount": 4900,
                        "currency": "usd",
                        "nickname": "Pro Plan",
                        "recurring": {"interval": "month"}
                    }
                }
            ]
        }
    }
    
    mock_canceled_sub = {
        "items": {
            "data": [
                {
                    "price": {"id": "price_123"}
                }
            ]
        }
    }

    class MockPager:
        def __init__(self, items):
            self.items = items
        def auto_paging_iter(self):
            return iter(self.items)

    with patch("stripe.Subscription.list") as mock_list:
        mock_list.side_effect = [
            MockPager([mock_active_sub, mock_active_sub]),
            MockPager([mock_canceled_sub])
        ]

        response = client.post("/setup/import-from-stripe", json={"stripe_key": "rk_test_12345"})
        assert response.status_code == 200
        data = response.json()
        assert data["detected_currency"] == "USD"
        assert len(data["tiers"]) == 1
        tier = data["tiers"][0]
        assert tier["name"] == "Pro Plan"
        assert tier["price"] == 49.0
        assert tier["user_count"] == 2
        # churn = 1 / (2 + 1) = 0.3333
        assert round(tier["churn_rate"], 2) == 0.33


def test_duplicate_company(client, mock_user):
    from datetime import datetime
    now = datetime.utcnow()
    company_id = uuid.uuid4()
    source_company = Company(
        id=company_id,
        user_id=mock_user.id,
        name="Source Company",
        industry="saas_b2b",
        currency="EUR",
        description="Original description",
        created_at=now,
    )
    source_tier = PricingTier(
        id=uuid.uuid4(),
        company_id=company_id,
        name="Tier A",
        price=100.0,
        billing_cycle="monthly",
        user_count=10,
        created_at=now,
    )
    source_feat = Feature(id=uuid.uuid4(), tier_id=source_tier.id, feature_name="Super Feature")
    source_tier.features = [source_feat]
    source_company.tiers = [source_tier]
    source_company.competitors = []

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.side_effect = [source_company, source_company]
    mock_db.execute.return_value = mock_res
    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.post(f"/companies/{company_id}/duplicate")
    assert response.status_code == 201


def test_sample_company_creation(client, mock_user):
    mock_db = AsyncMock()
    mock_res = MagicMock()
    # First call: not existing
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.post("/setup/sample-company")
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False
    assert data["name"] == "CloudHR Pro (sample)"
