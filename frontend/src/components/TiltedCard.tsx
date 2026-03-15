"use client";

import { useRef, useState } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";

interface TiltedCardProps {
  children: React.ReactNode;
  className?: string;
  tiltAmount?: number;
}

export default function TiltedCard({
  children,
  className = "",
  tiltAmount = 7,
}: TiltedCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [glarePos, setGlarePos] = useState({ x: 50, y: 50 });

  const mouseX = useMotionValue(0.5);
  const mouseY = useMotionValue(0.5);

  const springCfg = { stiffness: 280, damping: 28, mass: 0.4 };

  const rotateX = useSpring(
    useTransform(mouseY, [0, 1], [tiltAmount, -tiltAmount]),
    springCfg
  );
  const rotateY = useSpring(
    useTransform(mouseX, [0, 1], [-tiltAmount, tiltAmount]),
    springCfg
  );

  const glareOpacity = useMotionValue(0);
  const glareOpacitySpring = useSpring(glareOpacity, { stiffness: 200, damping: 25 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;
    mouseX.set(nx);
    mouseY.set(ny);
    setGlarePos({ x: nx * 100, y: ny * 100 });
  };

  const handleMouseEnter = () => glareOpacity.set(1);

  const handleMouseLeave = () => {
    mouseX.set(0.5);
    mouseY.set(0.5);
    glareOpacity.set(0);
  };

  return (
    <div
      ref={ref}
      className={`[perspective:900px] ${className}`}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <motion.div
        style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}
        className="relative h-full w-full"
      >
        {children}

        {/* Glare overlay */}
        <motion.div
          className="pointer-events-none absolute inset-0 rounded-xl overflow-hidden"
          style={{ opacity: glareOpacitySpring }}
        >
          <div
            className="absolute inset-0"
            style={{
              background: `radial-gradient(circle at ${glarePos.x}% ${glarePos.y}%, rgba(255,255,255,0.07) 0%, transparent 55%)`,
            }}
          />
        </motion.div>
      </motion.div>
    </div>
  );
}
