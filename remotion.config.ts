import {Config} from '@remotion/cli/config';

// Optimized for headless Linux container & YouTube H.264/AAC broadcast delivery
Config.setBrowserExecutable('/usr/local/bin/chromium');
Config.setChromiumOpenGlRenderer('swangle');
Config.setConcurrency(1);
Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(92);
Config.setPixelFormat('yuv420p');
Config.setCodec('h264');
Config.setCrf(18);
Config.setAudioCodec('aac');
Config.setAudioBitrate('192k');
Config.setOverwriteOutput(true);
