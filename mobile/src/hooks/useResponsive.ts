import { useEffect, useState } from 'react';
import { Dimensions, ScaledSize } from 'react-native';
import { DeviceLayoutInfo, getLayoutInfo } from '../utils/responsive';

export function useResponsive(): DeviceLayoutInfo {
  const [layoutInfo, setLayoutInfo] = useState<DeviceLayoutInfo>(() =>
    getLayoutInfo(Dimensions.get('window'))
  );

  useEffect(() => {
    function handleChange({ window }: { window: ScaledSize }) {
      setLayoutInfo(getLayoutInfo(window));
    }

    const subscription = Dimensions.addEventListener('change', handleChange);
    return () => subscription.remove();
  }, []);

  return layoutInfo;
}

