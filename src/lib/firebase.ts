import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider, OAuthProvider } from 'firebase/auth';

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// Check if Firebase config is available
const isFirebaseConfigured = firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId;

let app;
let auth;
let googleProvider;
let appleProvider;

if (isFirebaseConfigured) {
  app = initializeApp(firebaseConfig);
  auth = getAuth(app);
  googleProvider = new GoogleAuthProvider();
  appleProvider = new OAuthProvider('apple.com');
} else {
  console.warn('Firebase configuration is incomplete. Authentication features will be disabled.');
  auth = null;
  googleProvider = null;
  appleProvider = null;
}

export { auth, googleProvider, appleProvider };
export default app;
