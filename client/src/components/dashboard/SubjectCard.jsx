import { motion } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

const SubjectCard = ({ subject, onClick }) => {
  return (
    <motion.div whileHover={{ y: -2 }} transition={{ type: "spring", stiffness: 300, damping: 20 }}>
      <Card
        onClick={onClick}
        className="cursor-pointer hover:shadow-md transition-shadow"
      >
        <CardContent className="p-5 space-y-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="h-11 w-11 rounded-xl bg-muted grid place-items-center text-2xl">
                {subject.emoji}
              </div>
              <div>
                <p className="font-semibold leading-tight">{subject.name}</p>
                <p className="text-xs text-muted-foreground">
                  {subject.lessonsCompleted}/{subject.totalLessons} lessons
                </p>
              </div>
            </div>
            <Badge variant="secondary">{subject.mastery}%</Badge>
          </div>
          <div className="space-y-1.5">
            <Progress value={subject.mastery} />
            <p className="text-xs text-muted-foreground">Mastery</p>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
};

export default SubjectCard;
