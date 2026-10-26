export interface SubtitleCue {
  startSec: number;
  endSec: number;
  text: string;
}

export interface SceneItem {
  id: string;
  chapterTitle: string;
  headline: string;
  bullets: string[];
  durationSec: number;
  accentColor?: string;
  imageUrl?: string;
  statLabel?: string;
  statValue?: string;
}

export interface YouTubeStoryboardProps {
  channelName: string;
  channelTagline: string;
  episodeBadge: string;
  videoTitle: string;
  videoSubtitle: string;
  accentColor: string;
  secondaryColor: string;
  introDurationSec: number;
  outroDurationSec: number;
  scenes: SceneItem[];
  subtitles: SubtitleCue[];
  audioUrl?: string;
}
