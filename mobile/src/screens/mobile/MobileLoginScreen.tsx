import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import type { DataSource } from '../../api/dataSource';
import { colors as baseColors, type ThemePalette } from '../../theme/colors';
import { useThemeColors } from '../../theme/ThemeContext';

interface Props {
  source: DataSource;
  onLoginSuccess: () => void;
  onSwitchToDemo: () => void;
}

export const MobileLoginScreen: React.FC<Props> = ({
  source,
  onLoginSuccess,
  onSwitchToDemo,
}) => {
  const colors = useThemeColors(baseColors);
  const styles = createStyles(colors);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSignIn = async () => {
    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      await source.signIn(email, password);
      onLoginSuccess();
    } catch (err: any) {
      setError(err?.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.card}>
          <Text style={styles.title}>Oxygen Supply</Text>
          <Text style={styles.subtitle}>
            Clinical Monitoring Console. Sign in with your registered hospital staff account.
          </Text>

          {error ? <Text style={styles.errorText}>{error}</Text> : null}

          <TextInput
            style={styles.input}
            placeholder="Staff Email"
            placeholderTextColor={colors.muted}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
          />

          <TextInput
            style={styles.input}
            placeholder="Password"
            placeholderTextColor={colors.muted}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleSignIn}
            disabled={loading}
            activeOpacity={0.8}
          >
            {loading ? (
              <ActivityIndicator color={colors.surface} />
            ) : (
              <Text style={styles.buttonText}>Sign In</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.demoButton}
            onPress={onSwitchToDemo}
            activeOpacity={0.7}
          >
            <Text style={styles.demoButtonText}>Explore With Demo Simulator</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const createStyles = (colors: ThemePalette) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.page,
  },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
    borderWidth: 1,
    borderColor: colors.grid,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.ink,
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 13,
    color: colors.ink2,
    marginBottom: 16,
    lineHeight: 18,
  },
  input: {
    backgroundColor: colors.page, // Mirroring dashboard .login input: background: var(--page)
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 14,
    color: colors.ink,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: colors.grid,
  },
  button: {
    backgroundColor: colors.ink, // Mirroring dashboard button { background: var(--ink); color: var(--surface); }
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 6,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: colors.surface,
    fontSize: 14,
    fontWeight: '700',
  },
  demoButton: {
    marginTop: 14,
    paddingVertical: 8,
    alignItems: 'center',
  },
  demoButtonText: {
    color: colors.series, // Mirroring dashboard button.link: color: var(--series)
    fontSize: 13,
    fontWeight: '600',
  },
  errorText: {
    color: colors.critical,
    fontSize: 12,
    marginBottom: 12,
  },
});
