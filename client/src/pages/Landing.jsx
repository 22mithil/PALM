import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { z } from "zod";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { usePalmStore } from "@/store/usePalmStore";
import { register, login } from "@/lib/api";

const registerSchema = z.object({
  name: z.string().trim().min(1, { message: "Please enter your name" }).max(40),
  email: z.string().email({ message: "Please enter a valid email" }),
  password: z.string().min(8, { message: "Password must be at least 8 characters" }),
  grade: z.string().min(1, { message: "Please pick your grade" }),
});

const loginSchema = z.object({
  email: z.string().email({ message: "Please enter a valid email" }),
  password: z.string().min(1, { message: "Please enter your password" }),
});

const Landing = () => {
  const navigate = useNavigate();
  const storeLogin = usePalmStore((s) => s.login);
  const onboarded = usePalmStore((s) => s.onboarded);
  const nameRef = useRef(null);

  const [mode, setMode] = useState("register"); // "register" | "login"
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [grade, setGrade] = useState("");
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState("");

  // Redirect if already logged in
  useEffect(() => {
    if (onboarded) navigate("/dashboard", { replace: true });
  }, [onboarded, navigate]);

  useEffect(() => {
    nameRef.current?.focus();
    document.title = "PALM — Your AI Learning Companion";
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setApiError("");

    if (mode === "register") {
      const result = registerSchema.safeParse({ name, email, password, grade });
      if (!result.success) {
        const fieldErrors = {};
        result.error.issues.forEach((i) => { fieldErrors[i.path[0]] = i.message; });
        setErrors(fieldErrors);
        return;
      }
      setErrors({});
      setLoading(true);
      try {
        const data = await register({
          name: result.data.name,
          email: result.data.email,
          password: result.data.password,
          grade: Number(result.data.grade),
        });
        storeLogin(data.student, data.access_token);
        navigate("/dashboard", { replace: true });
      } catch (err) {
        setApiError(err.message);
      } finally {
        setLoading(false);
      }
    } else {
      const result = loginSchema.safeParse({ email, password });
      if (!result.success) {
        const fieldErrors = {};
        result.error.issues.forEach((i) => { fieldErrors[i.path[0]] = i.message; });
        setErrors(fieldErrors);
        return;
      }
      setErrors({});
      setLoading(true);
      try {
        const data = await login({
          email: result.data.email,
          password: result.data.password,
        });
        storeLogin(data.student, data.access_token);
        navigate("/dashboard", { replace: true });
      } catch (err) {
        setApiError(err.message);
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4 py-10">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="w-full max-w-md"
      >
        <Card className="rounded-2xl shadow-md">
          <CardContent className="p-6 md:p-8 space-y-6">
            {/* Branding */}
            <div className="text-center space-y-3">
              <div className="mx-auto h-12 w-12 rounded-2xl bg-primary text-primary-foreground grid place-items-center font-bold text-lg">
                P
              </div>
              <div className="space-y-1">
                <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">PALM</h1>
                <p className="text-sm text-muted-foreground">Your AI Learning Companion</p>
              </div>
            </div>

            {/* Intro */}
            <p className="text-base text-center text-muted-foreground">
              {mode === "register"
                ? "Create your account to start learning!"
                : "Welcome back! Sign in to continue."}
            </p>

            {/* API Error */}
            {apiError && (
              <div className="bg-destructive/10 text-destructive text-sm rounded-lg px-3 py-2 text-center">
                {apiError}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              {mode === "register" && (
                <div className="space-y-1.5">
                  <Label htmlFor="name">Your Name</Label>
                  <Input
                    id="name"
                    ref={nameRef}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter your name"
                    maxLength={40}
                    className="h-11 rounded-lg"
                    aria-invalid={!!errors.name}
                  />
                  {errors.name && (
                    <p className="text-xs text-destructive">{errors.name}</p>
                  )}
                </div>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  className="h-11 rounded-lg"
                  aria-invalid={!!errors.email}
                />
                {errors.email && (
                  <p className="text-xs text-destructive">{errors.email}</p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === "register" ? "At least 8 characters" : "Enter your password"}
                  className="h-11 rounded-lg"
                  aria-invalid={!!errors.password}
                />
                {errors.password && (
                  <p className="text-xs text-destructive">{errors.password}</p>
                )}
              </div>

              {mode === "register" && (
                <div className="space-y-1.5">
                  <Label htmlFor="grade">Select Grade</Label>
                  <Select value={grade} onValueChange={setGrade}>
                    <SelectTrigger id="grade" className="h-11 rounded-lg w-full">
                      <SelectValue placeholder="Pick your grade" />
                    </SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 4, 5].map((g) => (
                        <SelectItem key={g} value={String(g)}>
                          Grade {g}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {errors.grade && (
                    <p className="text-xs text-destructive">{errors.grade}</p>
                  )}
                </div>
              )}

              <Button
                type="submit"
                disabled={loading}
                className="w-full h-11 rounded-xl transition-transform hover:scale-[1.02] hover:shadow-md disabled:opacity-70 disabled:hover:scale-100"
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {mode === "register" ? "Creating account..." : "Signing in..."}
                  </>
                ) : (
                  mode === "register" ? "Start Learning" : "Sign In"
                )}
              </Button>
            </form>

            {/* Toggle mode */}
            <p className="text-center text-sm text-muted-foreground">
              {mode === "register" ? (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => { setMode("login"); setErrors({}); setApiError(""); }}
                    className="text-primary font-medium hover:underline"
                  >
                    Sign in
                  </button>
                </>
              ) : (
                <>
                  New here?{" "}
                  <button
                    type="button"
                    onClick={() => { setMode("register"); setErrors({}); setApiError(""); }}
                    className="text-primary font-medium hover:underline"
                  >
                    Create account
                  </button>
                </>
              )}
            </p>
          </CardContent>
        </Card>

        <p className="text-center text-xs text-muted-foreground mt-4">
          Friendly. Adaptive. Made for curious minds.
        </p>
      </motion.div>
    </div>
  );
};

export default Landing;
