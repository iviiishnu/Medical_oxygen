declare module 'react-native' {
  export type LayoutChangeEvent = any;
  export type GestureResponderEvent = any;
  export type ScaledSize = any;
  export type ScrollViewInstance = any;
  export type ViewProps = any;
  export type ColorValue = any;
  export type NativeSyntheticEvent<T> = any;
  export type EmitterSubscription = any;
  export const View: any;
  export const Text: any;
  export const StyleSheet: any;
  export const ScrollView: any;
  export const TouchableOpacity: any;
  export const TextInput: any;
  export const RefreshControl: any;
  export const Modal: any;
  export const TouchableWithoutFeedback: any;
  export const Dimensions: any;
  export const Switch: any;
  export const Alert: any;
  export const ActivityIndicator: any;
  export const Platform: any;
  export const FlatList: any;
  export const KeyboardAvoidingView: any;
  export const Image: any;
  export const PixelRatio: any;
  export const Vibration: any;
  export const TurboModuleRegistry: any;
  export const TurboModule: any;
  export const UIManager: any;
  export const requireNativeComponent: any;
  export const AppState: any;
  export const Linking: any;
  export const Share: any;
  export const StatusBar: any;
  const def: any;
  export default def;
}

declare module 'react-native-svg' {
  export const Svg: any;
  export const Path: any;
  export const Rect: any;
  export const Circle: any;
  export const Line: any;
  export const Polyline: any;
  export const G: any;
  export const Text: any;
  export default Svg;
}

declare module 'react-native-safe-area-context' {
  export const SafeAreaProvider: any;
  export const SafeAreaView: any;
  export const useSafeAreaInsets: () => { top: number; bottom: number; left: number; right: number };
}

declare module '@react-navigation/native' {
  export const useNavigation: <T = any>() => T;
  export const useRoute: <T = any>() => T;
  export const useIsFocused: () => boolean;
  export type RouteProp<T, K extends keyof T = any> = any;
  export const NavigationContainer: any;
  export const createNavigationContainerRef: any;
}

declare module '@react-navigation/bottom-tabs' {
  export const createBottomTabNavigator: <T = any>() => any;
}

declare module '@react-navigation/native-stack' {
  export const createNativeStackNavigator: <T = any>() => any;
  export type NativeStackNavigationProp<T = any, K extends keyof T = any> = any;
}

declare module '@react-navigation/drawer' {
  export const createDrawerNavigator: <T = any>() => any;
}
