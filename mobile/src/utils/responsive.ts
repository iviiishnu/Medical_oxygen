import { Dimensions, PixelRatio, ScaledSize } from 'react-native';

export interface DeviceLayoutInfo {
  isTablet: boolean;
  isLandscape: boolean;
  isPortrait: boolean;
  screenWidth: number;
  screenHeight: number;
  columns: number;
  gutter: number;
  cardWidth: number;
}

/**
 * Standard medical console breakpoint: >= 600 width is treated as tablet interface.
 */
export const TABLET_MIN_WIDTH = 600;

export function getLayoutInfo(dimensions: ScaledSize = Dimensions.get('window')): DeviceLayoutInfo {
  const { width, height } = dimensions;
  const isLandscape = width > height;
  const isPortrait = !isLandscape;
  const smallerDimension = Math.min(width, height);
  const isTablet = smallerDimension >= TABLET_MIN_WIDTH;

  let columns = 1;
  if (isTablet) {
    columns = isLandscape ? 3 : 2;
  } else if (isLandscape) {
    columns = 2;
  }

  const gutter = isTablet ? 16 : 12;
  const totalGutter = gutter * (columns + 1);
  const cardWidth = Math.floor((width - totalGutter) / columns);

  return {
    isTablet,
    isLandscape,
    isPortrait,
    screenWidth: width,
    screenHeight: height,
    columns,
    gutter,
    cardWidth,
  };
}

/**
 * Normalized scale based on standard mobile viewport (375x812)
 */
const { width: SCREEN_WIDTH } = Dimensions.get('window');
const scale = SCREEN_WIDTH / 375;

export function normalize(size: number): number {
  const newSize = size * scale;
  return Math.round(PixelRatio.roundToNearestPixel(newSize));
}

