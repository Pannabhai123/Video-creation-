import React from 'react';
import {AbsoluteFill, Audio, Composition, Sequence, useVideoConfig} from 'remotion';
import {AnimatedIntro, AnimatedIntroProps} from './components/AnimatedIntro';
import {SceneCard} from './components/SceneCard';
import {SubtitleOverlay} from './components/SubtitleOverlay';
import {YouTubeEndScreen, YouTubeEndScreenProps} from './components/YouTubeEndScreen';
import {YouTubeThumbnail, YouTubeThumbnailProps} from './components/YouTubeThumbnail';
import {YouTubeStoryboardProps} from './types';

const defaultStoryboard: YouTubeStoryboardProps = {
  channelName: 'Nexus Tech Studio',
  channelTagline: 'Automated AI Video Engineering & Production',
  episodeBadge: 'SYSTEM DEMO',
  videoTitle: 'Automated YouTube Video Production Pipeline',
  videoSubtitle: 'End-to-End Script, Voiceover, Motion Graphics, Subtitles & 1080p/4K Mastering',
  accentColor: '#38BDF8',
  secondaryColor: '#818CF8',
  introDurationSec: 3.5,
  outroDurationSec: 4.0,
  scenes: [
    {
      id: 'scene-1',
      chapterTitle: 'Pipeline Architecture',
      headline: 'Unified Python + FFmpeg + Remotion Stack',
      bullets: [
        'Automated storyboarding, voiceover & broadcast -14 LUFS mastering',
        'React spring animations combined with OpenCV & MoviePy compositing',
      ],
      durationSec: 4.5,
      statValue: '1080p',
      statLabel: 'H.264 + AAC Broadcast Ready',
    },
    {
      id: 'scene-2',
      chapterTitle: 'Smart Subtitles & Audio',
      headline: 'Synchronized Captions & Auto-Ducked Music',
      bullets: [
        'Word-timed SRT, WebVTT & styled ASS captions generated automatically',
        'Copyright-safe procedural soundtrack ducks smoothly under speech',
      ],
      durationSec: 4.5,
      statValue: '-14 LUFS',
      statLabel: 'YouTube Loudness Standard',
    },
  ],
  subtitles: [
    {startSec: 0.4, endSec: 3.3, text: 'Welcome to the Automated YouTube Video Production Studio.'},
    {startSec: 3.7, endSec: 7.9, text: 'Every scene combines programmatic motion graphics with broadcast encoding.'},
    {startSec: 8.2, endSec: 12.3, text: 'Background music ducks automatically beneath synchronized subtitles.'},
    {startSec: 12.6, endSec: 16.2, text: 'Subscribe for more automated long-form engineering tutorials!'},
  ],
};

export const YouTubeShowcaseVideo: React.FC<YouTubeStoryboardProps> = (props) => {
  const {fps} = useVideoConfig();
  const introFrames = Math.max(1, Math.round(props.introDurationSec * fps));
  const outroFrames = Math.max(1, Math.round(props.outroDurationSec * fps));

  let cursor = introFrames;

  return (
    <AbsoluteFill style={{backgroundColor: '#050811'}}>
      {props.audioUrl ? <Audio src={props.audioUrl} /> : null}

      <Sequence from={0} durationInFrames={introFrames}>
        <AnimatedIntro
          channelName={props.channelName}
          episodeBadge={props.episodeBadge}
          videoTitle={props.videoTitle}
          videoSubtitle={props.videoSubtitle}
          accentColor={props.accentColor}
          secondaryColor={props.secondaryColor}
        />
      </Sequence>

      {props.scenes.map((scene, idx) => {
        const sceneFrames = Math.max(1, Math.round(scene.durationSec * fps));
        const from = cursor;
        cursor += sceneFrames;
        return (
          <Sequence key={scene.id} from={from} durationInFrames={sceneFrames}>
            <SceneCard
              scene={scene}
              sceneIndex={idx}
              totalScenes={props.scenes.length}
              defaultAccent={props.accentColor}
              secondaryColor={props.secondaryColor}
            />
          </Sequence>
        );
      })}

      <Sequence from={cursor} durationInFrames={outroFrames}>
        <YouTubeEndScreen
          channelName={props.channelName}
          channelTagline={props.channelTagline}
          accentColor={props.accentColor}
          secondaryColor={props.secondaryColor}
        />
      </Sequence>

      <SubtitleOverlay cues={props.subtitles} accentColor={props.accentColor} />
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  const fps = 30;
  return (
    <>
      <Composition
        id="AnimatedIntro"
        component={AnimatedIntro as unknown as React.FC<Record<string, unknown>>}
        durationInFrames={105}
        fps={fps}
        width={1920}
        height={1080}
        defaultProps={
          {
            channelName: defaultStoryboard.channelName,
            episodeBadge: defaultStoryboard.episodeBadge,
            videoTitle: defaultStoryboard.videoTitle,
            videoSubtitle: defaultStoryboard.videoSubtitle,
            accentColor: defaultStoryboard.accentColor,
            secondaryColor: defaultStoryboard.secondaryColor,
          } satisfies AnimatedIntroProps
        }
        calculateMetadata={({props}) => {
          const p = props as Record<string, unknown>;
          const outFps = Number(p.fps) || fps;
          const durSec = Number(p.durationSec) || 3.5;
          return {
            fps: outFps,
            width: Number(p.width) || 1920,
            height: Number(p.height) || 1080,
            durationInFrames: Math.max(15, Math.round(durSec * outFps)),
          };
        }}
      />

      <Composition
        id="AnimatedEndScreen"
        component={YouTubeEndScreen as unknown as React.FC<Record<string, unknown>>}
        durationInFrames={120}
        fps={fps}
        width={1920}
        height={1080}
        defaultProps={
          {
            channelName: defaultStoryboard.channelName,
            channelTagline: defaultStoryboard.channelTagline,
            accentColor: defaultStoryboard.accentColor,
            secondaryColor: defaultStoryboard.secondaryColor,
          } satisfies YouTubeEndScreenProps
        }
        calculateMetadata={({props}) => {
          const p = props as Record<string, unknown>;
          const outFps = Number(p.fps) || fps;
          const durSec = Number(p.durationSec) || 4.0;
          return {
            fps: outFps,
            width: Number(p.width) || 1920,
            height: Number(p.height) || 1080,
            durationInFrames: Math.max(15, Math.round(durSec * outFps)),
          };
        }}
      />

      <Composition
        id="YouTubeShowcase"
        component={YouTubeShowcaseVideo as unknown as React.FC<Record<string, unknown>>}
        fps={fps}
        width={1920}
        height={1080}
        durationInFrames={495}
        defaultProps={defaultStoryboard as unknown as Record<string, unknown>}
        calculateMetadata={({props}) => {
          const p = props as unknown as YouTubeStoryboardProps;
          const scenesSec = (p.scenes || []).reduce((acc, s) => acc + s.durationSec, 0);
          const totalSec = (p.introDurationSec || 3.5) + scenesSec + (p.outroDurationSec || 4.0);
          return {
            durationInFrames: Math.max(30, Math.round(totalSec * fps)),
          };
        }}
      />

      <Composition
        id="YouTubeThumbnail"
        component={YouTubeThumbnail as unknown as React.FC<Record<string, unknown>>}
        durationInFrames={1}
        fps={1}
        width={1920}
        height={1080}
        defaultProps={
          {
            title: 'आदतों और अनुशासन का मनोविज्ञान',
            badgeText: 'बुक समरी',
            channelName: defaultStoryboard.channelName,
            accentColor: defaultStoryboard.accentColor,
            secondaryColor: defaultStoryboard.secondaryColor,
          } satisfies YouTubeThumbnailProps
        }
      />
    </>
  );
};
