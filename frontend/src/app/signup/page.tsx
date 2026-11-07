"use client";

import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { SignIn, SignUp } from "@clerk/nextjs";
import { useAuth } from "@/contexts/AuthContext";

export default function SignUpPage() {
  return (
    // useSearchParams needs a Suspense boundary on a statically built page.
    <Suspense>
      <ClerkSignInPage />
    </Suspense>
  );
}

/** Sign in and sign up with Clerk's own forms; ?mode=signup shows sign-up. */
function ClerkSignInPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const mode = useSearchParams().get("mode") === "signup" ? "signup" : "signin";

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [user, loading, router]);

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-16">
      {mode === "signup" ? (
        <SignUp routing="hash" signInUrl="/signup" forceRedirectUrl="/dashboard" />
      ) : (
        <SignIn routing="hash" signUpUrl="/signup?mode=signup" forceRedirectUrl="/dashboard" />
      )}
    </div>
  );
}
