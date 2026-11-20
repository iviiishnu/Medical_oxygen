import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Circle, G } from 'react-native-svg';
import { colors } from '../theme/colors';

interface Props {
  percentage: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  bgTrackColor?: string;
}

export const CircularDonutMeter: React.FC<Props> = ({
  percentage,
  size = 90,
  strokeWidth = 10,
  color = colors.normal,
  bgTrackColor = '#e2e8f0',
}) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (circumference * percentage) / 100;

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <G rotation="-90" origin={`${size / 2}, ${size / 2}`}>
          {/* Background circle track */}
          <Circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={bgTrackColor}
            strokeWidth={strokeWidth}
            fill="none"
          />
          {/* Animated/filled progress arc */}
          <Circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="none"
          />
        </G>
      </Svg>
      <View style={StyleSheet.absoluteFillObject} pointerEvents="none">
        <View style={styles.centerWrap}>
          <Text style={styles.percentageText}>{percentage}%</Text>
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  centerWrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  percentageText: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.ink,
  },
});
