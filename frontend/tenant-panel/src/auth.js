import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
} from 'amazon-cognito-identity-js';

const STORAGE_KEY = 'botman_tenant_cognito_session';

export function getTenantIdFromPath() {
  const [, tenantId] = window.location.pathname.split('/');
  return tenantId || 'demo-tenant';
}

export const TENANT_ID = getTenantIdFromPath();
const USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID || '';
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || '';

let pendingNewPasswordUser = null;

function requireCognitoConfig() {
  if (!USER_POOL_ID || !CLIENT_ID) {
    throw new Error('Missing VITE_COGNITO_USER_POOL_ID or VITE_COGNITO_CLIENT_ID');
  }
}

function userPool() {
  requireCognitoConfig();
  return new CognitoUserPool({
    UserPoolId: USER_POOL_ID,
    ClientId: CLIENT_ID,
  });
}

function buildSession({ email, idToken, accessToken, refreshToken, expiresAt }) {
  return {
    email,
    tenantId: TENANT_ID,
    token: idToken,
    idToken,
    accessToken,
    refreshToken,
    expiresAt,
    createdAt: new Date().toISOString(),
  };
}

function saveSession(session) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  return session;
}

export function getSession() {
  try {
    const session = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (!session?.token) return null;
    if (session.expiresAt && new Date(session.expiresAt).getTime() <= Date.now()) {
      logout();
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function getToken() {
  return getSession()?.token || '';
}

export function hasPendingNewPasswordChallenge() {
  return Boolean(pendingNewPasswordUser);
}

export async function login({ email, password }) {
  const normalizedEmail = String(email || '').trim().toLowerCase();
  const normalizedPassword = String(password || '');

  if (!/^\S+@\S+\.\S+$/.test(normalizedEmail)) {
    throw new Error('Enter a valid email address.');
  }
  if (!normalizedPassword) {
    throw new Error('Password is required.');
  }

  const cognitoUser = new CognitoUser({
    Username: normalizedEmail,
    Pool: userPool(),
  });
  const authDetails = new AuthenticationDetails({
    Username: normalizedEmail,
    Password: normalizedPassword,
  });

  return new Promise((resolve, reject) => {
    cognitoUser.authenticateUser(authDetails, {
      onSuccess: (result) => {
        pendingNewPasswordUser = null;
        const idToken = result.getIdToken();
        const accessToken = result.getAccessToken();
        const session = buildSession({
          email: idToken.payload?.email || normalizedEmail,
          idToken: idToken.getJwtToken(),
          accessToken: accessToken.getJwtToken(),
          refreshToken: result.getRefreshToken()?.getToken(),
          expiresAt: new Date(idToken.getExpiration() * 1000).toISOString(),
        });
        resolve(saveSession(session));
      },
      onFailure: (err) => {
        pendingNewPasswordUser = null;
        reject(new Error(err?.message || 'Login failed.'));
      },
      newPasswordRequired: () => {
        pendingNewPasswordUser = cognitoUser;
        const challenge = new Error('NEW_PASSWORD_REQUIRED');
        challenge.code = 'NEW_PASSWORD_REQUIRED';
        reject(challenge);
      },
    });
  });
}

export async function completeNewPassword({ email, newPassword }) {
  const normalizedEmail = String(email || '').trim().toLowerCase();
  const normalizedPassword = String(newPassword || '');
  if (!pendingNewPasswordUser) {
    throw new Error('No active password change challenge. Log in again with the temporary password.');
  }
  if (normalizedPassword.length < 10) {
    throw new Error('New password must have at least 10 characters.');
  }

  return new Promise((resolve, reject) => {
    pendingNewPasswordUser.completeNewPasswordChallenge(normalizedPassword, {}, {
      onSuccess: (result) => {
        pendingNewPasswordUser = null;
        const idToken = result.getIdToken();
        const accessToken = result.getAccessToken();
        const session = buildSession({
          email: idToken.payload?.email || normalizedEmail,
          idToken: idToken.getJwtToken(),
          accessToken: accessToken.getJwtToken(),
          refreshToken: result.getRefreshToken()?.getToken(),
          expiresAt: new Date(idToken.getExpiration() * 1000).toISOString(),
        });
        resolve(saveSession(session));
      },
      onFailure: (err) => reject(new Error(err?.message || 'Password change failed.')),
    });
  });
}

export function logout() {
  try {
    const session = getSession();
    if (session?.email && USER_POOL_ID && CLIENT_ID) {
      const user = new CognitoUser({ Username: session.email, Pool: userPool() });
      user.signOut();
    }
  } catch {
    // Local cleanup is enough for the SPA.
  }
  pendingNewPasswordUser = null;
  localStorage.removeItem(STORAGE_KEY);
}
