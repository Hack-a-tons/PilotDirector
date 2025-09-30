'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { User, onAuthStateChanged, signInWithPopup, signOut } from 'firebase/auth';
import { auth, googleProvider, appleProvider } from '@/lib/firebase';

interface UserContextType {
  user: User | null;
  userId: string;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithApple: () => Promise<void>;
  logout: () => Promise<void>;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Generate browser-based ID for anonymous users
  const getBrowserId = () => {
    if (typeof window === 'undefined') return 'browser-temp';
    
    let browserId = localStorage.getItem('pilot-director-browser-id');
    if (!browserId) {
      browserId = 'browser-' + Math.random().toString(36).substr(2, 9);
      localStorage.setItem('pilot-director-browser-id', browserId);
    }
    return browserId;
  };

  const userId = user?.uid || getBrowserId();

  useEffect(() => {
    if (!auth) {
      setLoading(false);
      return;
    }
    
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setUser(user);
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const signInWithGoogle = async () => {
    if (!auth || !googleProvider) {
      console.warn('Firebase not configured');
      return;
    }
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (error) {
      console.error('Google sign in error:', error);
    }
  };

  const signInWithApple = async () => {
    if (!auth || !appleProvider) {
      console.warn('Firebase not configured');
      return;
    }
    try {
      await signInWithPopup(auth, appleProvider);
    } catch (error) {
      console.error('Apple sign in error:', error);
    }
  };

  const logout = async () => {
    if (!auth) {
      console.warn('Firebase not configured');
      return;
    }
    try {
      await signOut(auth);
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  return (
    <UserContext.Provider value={{
      user,
      userId,
      loading,
      signInWithGoogle,
      signInWithApple,
      logout
    }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
}
