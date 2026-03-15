"use client";

import { motion } from "framer-motion";

interface BlurTextProps {
  text: string;
  className?: string;
  delay?: number;
  wordClassName?: string;
}

export default function BlurText({
  text,
  className = "",
  delay = 0.05,
  wordClassName = "",
}: BlurTextProps) {
  const words = text.split(" ");

  const containerVariants = {
    hidden: {},
    visible: {
      transition: {
        staggerChildren: delay,
      },
    },
  };

  const wordVariants = {
    hidden: {
      opacity: 0,
      filter: "blur(16px)",
      y: 12,
    },
    visible: {
      opacity: 1,
      filter: "blur(0px)",
      y: 0,
      transition: {
        duration: 0.6,
        ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
      },
    },
  };

  return (
    <motion.span
      className={`inline ${className}`}
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      aria-label={text}
    >
      {words.map((word, i) => (
        <motion.span
          key={i}
          className={`inline-block ${wordClassName}`}
          variants={wordVariants}
          style={{ marginRight: i < words.length - 1 ? "0.25em" : undefined }}
        >
          {word}
        </motion.span>
      ))}
    </motion.span>
  );
}
