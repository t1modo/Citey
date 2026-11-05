import { initializeApp, getApps, getApp, FirebaseApp } from "firebase/app";
import { getAuth, Auth } from "firebase/auth";

// Each NEXT_PUBLIC_* variable must be referenced literally so Next.js can
// inline it into the browser bundle.
const firebaseConfig = {
  apiKey:            process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain:        process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId:         process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket:     process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId:             process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// Without these Firebase throws an opaque "auth/invalid-api-key". Say which
// variables are missing and how to provide them instead.
const required: [string, string | undefined][] = [
  ["NEXT_PUBLIC_FIREBASE_API_KEY", firebaseConfig.apiKey],
  ["NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN", firebaseConfig.authDomain],
  ["NEXT_PUBLIC_FIREBASE_PROJECT_ID", firebaseConfig.projectId],
];
const missing = required.filter(([, value]) => !value).map(([name]) => name);
if (missing.length > 0) {
  throw new Error(
    `Missing Firebase config: ${missing.join(", ")}. ` +
      "Copy frontend/.env.example to frontend/.env.local, fill in the values from " +
      "Firebase console > Project settings > Your apps, then restart `npm run dev`.",
  );
}

const app: FirebaseApp =
  getApps().length === 0 ? initializeApp(firebaseConfig) : getApp();

const auth: Auth = getAuth(app);

export { app, auth };
