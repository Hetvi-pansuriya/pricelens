import React, { createContext, useContext, useState, useEffect } from 'react';
import { authApi } from '../api/auth';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(() => localStorage.getItem('pricelens_token'));
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('pricelens_user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      const storedToken = localStorage.getItem('pricelens_token');
      if (storedToken) {
        try {
          const profile = await authApi.getMe();
          setUser(profile);
          localStorage.setItem('pricelens_user', JSON.stringify(profile));
        } catch {
          // Token is invalid/expired
          localStorage.removeItem('pricelens_token');
          localStorage.removeItem('pricelens_user');
          setToken(null);
          setUser(null);
        }
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  const login = async (credentials) => {
    const data = await authApi.login(credentials);
    const jwt = data.access_token;
    localStorage.setItem('pricelens_token', jwt);
    setToken(jwt);
    try {
      const profile = await authApi.getMe();
      setUser(profile);
      localStorage.setItem('pricelens_user', JSON.stringify(profile));
      return profile;
    } catch {
      // Fallback if /auth/me fails but login succeeded
      const fallbackUser = { email: credentials.email };
      setUser(fallbackUser);
      localStorage.setItem('pricelens_user', JSON.stringify(fallbackUser));
      return fallbackUser;
    }
  };

  const signup = async (userData) => {
    const data = await authApi.signup(userData);
    const jwt = data.access_token;
    localStorage.setItem('pricelens_token', jwt);
    setToken(jwt);
    try {
      const profile = await authApi.getMe();
      setUser(profile);
      localStorage.setItem('pricelens_user', JSON.stringify(profile));
      return profile;
    } catch {
      const fallbackUser = { email: userData.email };
      setUser(fallbackUser);
      localStorage.setItem('pricelens_user', JSON.stringify(fallbackUser));
      return fallbackUser;
    }
  };

  const logout = () => {
    localStorage.removeItem('pricelens_token');
    localStorage.removeItem('pricelens_user');
    setToken(null);
    setUser(null);
    window.location.href = '/login';
  };

  const deleteAccount = async () => {
    await authApi.deleteAccount();
    logout();
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        isAuthenticated: !!token,
        loading,
        login,
        signup,
        logout,
        deleteAccount,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
