import { motion } from "framer-motion";
import { Clock, CheckCircle2, Play } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { usePalmStore } from "@/store/usePalmStore";

const difficultyVariant = {
  Easy: "secondary",
  Medium: "outline",
  Hard: "default",
};

const LessonCard = ({ lesson }) => {
  const subject = usePalmStore((s) => s.subjects.find((sub) => sub.id === lesson.subjectId));
  const completeLesson = usePalmStore((s) => s.completeLesson);

  return (
    <motion.div whileHover={{ y: -2 }} transition={{ type: "spring", stiffness: 300, damping: 20 }}>
      <Card className="hover:shadow-md transition-shadow h-full">
        <CardContent className="p-5 flex flex-col h-full gap-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xl">{subject?.emoji}</span>
              <span className="text-xs text-muted-foreground font-medium">{subject?.name}</span>
            </div>
            <Badge variant={difficultyVariant[lesson.difficulty]}>{lesson.difficulty}</Badge>
          </div>

          <div className="space-y-1.5 flex-1">
            <h3 className="font-semibold leading-snug">{lesson.title}</h3>
            <p className="text-sm text-muted-foreground line-clamp-2">{lesson.description}</p>
          </div>

          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              {lesson.duration} min
            </div>
            {lesson.completed ? (
              <Badge variant="secondary" className="gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" /> Done
              </Badge>
            ) : (
              <Button size="sm" onClick={() => completeLesson(lesson.id)} className="gap-1">
                <Play className="h-3.5 w-3.5" /> Start
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
};

export default LessonCard;
