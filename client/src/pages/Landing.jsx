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

const schema = z.object({
  name: z.string().trim().min(1, { message: "Please enter your name" }).max(40, { message: "Name must be under 40 characters" }),
  grade: z.string().min(1, { message: "Please pick your grade" }),
});

const Landing = () => {
  const navigate = useNavigate();
  const completeOnboarding = usePalmStore((s) => s.completeOnboarding);
  const nameRef = useRef(null);

  const [name, setName] = useState("");
  const [grade, setGrade] = useState("");
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    nameRef.current?.focus();
    document.title = "PALM — Your AI Learning Companion";
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    const result = schema.safeParse({ name, grade });
    if (!result.success) {
      const fieldErrors = {};
      result.error.issues.forEach((i) => {
        const k = i.path[0];
        fieldErrors[k] = i.message;
      });
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    setLoading(true);
    setTimeout(() => {
      completeOnboarding(result.data.name, Number(result.data.grade));
      navigate("/dashboard", { replace: true });
    }, 700);
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
              Let's start your learning journey!
            </p>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
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

              <Button
                type="submit"
                disabled={loading}
                className="w-full h-11 rounded-xl transition-transform hover:scale-[1.02] hover:shadow-md disabled:opacity-70 disabled:hover:scale-100"
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Getting ready...
                  </>
                ) : (
                  "Start Learning"
                )}
              </Button>
            </form>
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
