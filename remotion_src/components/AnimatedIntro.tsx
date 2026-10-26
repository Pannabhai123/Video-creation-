import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export interface AnimatedIntroProps {
  channelName: string;
  episodeBadge: string;
  videoTitle: string;
  videoSubtitle: string;
  accentColor: string;
  secondaryColor: string;
}

export const AnimatedIntro: React.FC<AnimatedIntroProps> = ({
  channelName,
  episodeBadge,
  videoTitle,
  videoSubtitle,
  accentColor,
  secondaryColor,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const badgeSpring = spring({frame, fps, config: {damping: 14, stiffness: 120}});
  const titleSpring = spring({frame: Math.max(0, frame - 8), fps, config: {damping: 16, stiffness: 110}});
  const subSpring = spring({frame: Math.max(0, frame - 18), fps, config: {damping: 18, stiffness: 100}});
  const lineExpand = interpolate(frame, [6, 32], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const exitOpacity = interpolate(
    frame,
    [durationInFrames - 12, durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );

  const glowShift = interpolate(frame, [0, durationInFrames], [-40, 40]);

  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(circle at 20% 25%, #172554 0%, #0B1120 58%, #050811 100%)',
        fontFamily: '"Poppins", "DejaVu Sans", sans-serif',
        color: '#F8FAFC',
        overflow: 'hidden',
        opacity: exitOpacity,
      }}
    >
      {/* Subtle architectural grid */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage:
            'linear-gradient(rgba(148,163,184,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.07) 1px, transparent 1px)',
          backgroundSize: '72px 72px',
          transform: `translateX(${glowShift * 0.4}px)`,
        }}
      />

      {/* Ambient glow orbs */}
      <div
        style={{
          position: 'absolute',
          width: 640,
          height: 640,
          borderRadius: '50%',
          background: `radial-gradient(circle, ${accentColor}33 0%, transparent 70%)`,
          top: -180,
          right: -100 + glowShift,
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 540,
          height: 540,
          borderRadius: '50%',
          background: `radial-gradient(circle, ${secondaryColor}2B 0%, transparent 70%)`,
          bottom: -180,
          left: -80 - glowShift,
        }}
      />

      <AbsoluteFill style={{padding: '110px 140px', justifyContent: 'center'}}>
        {/* Top Channel + Episode Pill */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 18,
            transform: `translateY(${(1 - badgeSpring) * 28}px)`,
            opacity: badgeSpring,
            marginBottom: 28,
          }}
        >
          <span
            style={{
              backgroundColor: accentColor,
              color: '#08101D',
              padding: '8px 20px',
              borderRadius: 999,
              fontWeight: 800,
              fontSize: 22,
              letterSpacing: 1.6,
              textTransform: 'uppercase',
            }}
          >
            {episodeBadge}
          </span>
          <span
            style={{
              color: '#94A3B8',
              fontSize: 24,
              fontWeight: 600,
              letterSpacing: 1.2,
              textTransform: 'uppercase',
            }}
          >
            {channelName}
          </span>
        </div>

        {/* Main Kinetic Headline */}
        <h1
          style={{
            fontSize: 82,
            lineHeight: 1.08,
            fontWeight: 800,
            margin: 0,
            maxWidth: 1480,
            letterSpacing: -1.2,
            transform: `translateY(${(1 - titleSpring) * 40}px)`,
            opacity: titleSpring,
          }}
        >
          {videoTitle}
        </h1>

        {/* Animated Gradient Accent Rule */}
        <div
          style={{
            height: 7,
            width: 440 * lineExpand,
            borderRadius: 99,
            background: `linear-gradient(90deg, ${accentColor}, ${secondaryColor})`,
            marginTop: 34,
            marginBottom: 30,
          }}
        />

        {/* Subtitle */}
        <p
          style={{
            fontSize: 34,
            lineHeight: 1.4,
            color: '#CBD5E1',
            margin: 0,
            maxWidth: 1280,
            fontWeight: 500,
            transform: `translateY(${(1 - subSpring) * 26}px)`,
            opacity: subSpring,
          }}
        >
          {videoSubtitle}
        </p>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
