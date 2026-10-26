import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {SceneItem} from '../types';

interface SceneCardProps {
  scene: SceneItem;
  sceneIndex: number;
  totalScenes: number;
  defaultAccent: string;
  secondaryColor: string;
}

export const SceneCard: React.FC<SceneCardProps> = ({
  scene,
  sceneIndex,
  totalScenes,
  defaultAccent,
  secondaryColor,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const accent = scene.accentColor || defaultAccent;

  const headerSpring = spring({frame, fps, config: {damping: 16, stiffness: 120}});
  const cardScale = interpolate(frame, [0, durationInFrames], [1.0, 1.055], {
    extrapolateRight: 'clamp',
  });
  const progress = interpolate(frame, [0, durationInFrames], [0, 100], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        background: 'linear-gradient(135deg, #090E1A 0%, #111C33 55%, #0B1324 100%)',
        fontFamily: '"Poppins", "DejaVu Sans", sans-serif',
        color: '#F8FAFC',
        padding: '78px 104px 130px 104px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}
    >
      {/* Top Chapter Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          opacity: headerSpring,
          transform: `translateY(${(1 - headerSpring) * -18}px)`,
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', gap: 16}}>
          <div
            style={{
              backgroundColor: `${accent}26`,
              border: `2px solid ${accent}`,
              color: accent,
              padding: '6px 18px',
              borderRadius: 999,
              fontSize: 21,
              fontWeight: 700,
              letterSpacing: 1.1,
            }}
          >
            CHAPTER 0{sceneIndex + 1} / 0{totalScenes}
          </div>
          <span style={{fontSize: 24, color: '#94A3B8', fontWeight: 600}}>
            {scene.chapterTitle}
          </span>
        </div>

        {/* Scene progress indicator */}
        <div
          style={{
            width: 240,
            height: 8,
            backgroundColor: 'rgba(148,163,184,0.2)',
            borderRadius: 99,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: '100%',
              background: `linear-gradient(90deg, ${accent}, ${secondaryColor})`,
            }}
          />
        </div>
      </div>

      {/* Main Split Content Grid */}
      <div
        style={{
          display: 'flex',
          gap: 64,
          alignItems: 'center',
          flex: 1,
          marginTop: 36,
        }}
      >
        {/* Left Column: Kinetic Headline + Staggered Bullets */}
        <div style={{flex: 1.15, display: 'flex', flexDirection: 'column', gap: 26}}>
          <h2
            style={{
              fontSize: 58,
              lineHeight: 1.14,
              fontWeight: 800,
              margin: 0,
              color: '#FFFFFF',
            }}
          >
            {scene.headline}
          </h2>

          <div style={{display: 'flex', flexDirection: 'column', gap: 18, marginTop: 8}}>
            {scene.bullets.map((bullet, idx) => {
              const delay = 10 + idx * 14;
              const bSpring = spring({
                frame: Math.max(0, frame - delay),
                fps,
                config: {damping: 15, stiffness: 115},
              });
              return (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 18,
                    backgroundColor: 'rgba(15, 23, 42, 0.78)',
                    borderLeft: `6px solid ${accent}`,
                    padding: '18px 24px',
                    borderRadius: 14,
                    transform: `translateX(${(1 - bSpring) * -32}px)`,
                    opacity: bSpring,
                    boxShadow: '0 10px 30px rgba(0,0,0,0.28)',
                  }}
                >
                  <div
                    style={{
                      width: 14,
                      height: 14,
                      borderRadius: '50%',
                      backgroundColor: accent,
                      flexShrink: 0,
                    }}
                  />
                  <span style={{fontSize: 28, color: '#E2E8F0', fontWeight: 500, lineHeight: 1.32}}>
                    {bullet}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Visual / Metric Showcase Card with subtle Ken Burns */}
        <div
          style={{
            flex: 0.85,
            height: 500,
            borderRadius: 28,
            overflow: 'hidden',
            position: 'relative',
            border: '2px solid rgba(148,163,184,0.22)',
            background: `radial-gradient(circle at 30% 20%, ${accent}30, #0F172A 75%)`,
            boxShadow: '0 24px 60px rgba(0,0,0,0.45)',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          {scene.imageUrl ? (
            <Img
              src={scene.imageUrl}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                transform: `scale(${cardScale})`,
              }}
            />
          ) : (
            <div
              style={{
                transform: `scale(${cardScale})`,
                textAlign: 'center',
                padding: 40,
              }}
            >
              <div
                style={{
                  fontSize: 96,
                  fontWeight: 900,
                  color: accent,
                  letterSpacing: -2,
                  lineHeight: 1,
                }}
              >
                {scene.statValue || `0${sceneIndex + 1}`}
              </div>
              <div
                style={{
                  marginTop: 18,
                  fontSize: 28,
                  fontWeight: 600,
                  color: '#CBD5E1',
                  textTransform: 'uppercase',
                  letterSpacing: 1.5,
                }}
              >
                {scene.statLabel || scene.chapterTitle}
              </div>
            </div>
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};
