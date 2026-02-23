/**
 * API service layer — all calls to the Moltbot FastAPI backend.
 *
 * In development, Vite proxies /api → https://moltbot-fastapi.onrender.com
 * In production, we use the VITE_API_URL env variable.
 */

const BASE =
    import.meta.env.VITE_API_URL
        ? `${import.meta.env.VITE_API_URL}/api/v1`
        : '/api/v1';

async function request(path, options = {}) {
    const url = `${BASE}${path}`;
    const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    const json = await res.json();
    return json;
}

/* =================== Playground Users =================== */

/**
 * Get list of existing playground users from tbl_clawdbot_users.
 */
export async function getPlaygroundUsers() {
    try {
        const res = await request('/playground/users');
        if (res.code === 200 && res.data?.users) {
            return res.data.users;
        }
    } catch {
        // API unreachable
    }
    return [];
}

/**
 * Create a new playground user and get OAuth URL.
 */
export async function createPlaygroundUser(name, redirectUri, timezone = 'UTC') {
    return request('/playground/create-user', {
        method: 'POST',
        body: JSON.stringify({ name, redirect_uri: redirectUri, timezone }),
    });
}

/**
 * Update a user's timezone setting.
 */
export async function updateUserTimezone(userId, timezone) {
    return request(`/playground/users/${userId}/timezone`, {
        method: 'PATCH',
        body: JSON.stringify({ timezone }),
    });
}

/* =================== OAuth =================== */

export async function getOAuthInitUrl(userId, redirectUri) {
    const params = new URLSearchParams({ user_id: userId });
    if (redirectUri) params.set('redirect_uri', redirectUri);
    return request(`/oauth/google/init?${params.toString()}`);
}

export async function getOAuthStatus(userId) {
    return request(`/oauth/google/status/${userId}`);
}

/* =================== Chat / Execute =================== */

export async function executeAction(userId, message, timezone = 'UTC', context = '') {
    return request('/execute-action', {
        method: 'POST',
        body: JSON.stringify({
            user_id: userId,
            message,
            timezone,
            context,
        }),
    });
}

/* =================== Session =================== */

export async function getSession(userId) {
    return request(`/session/${userId}`);
}

export async function getConversationHistory(userId, limit = 30) {
    return request(`/session/${userId}/history?limit=${limit}`);
}

export async function clearSession(userId) {
    return request(`/session/${userId}`, { method: 'DELETE' });
}

/* =================== Credentials =================== */

export async function getCredentialsStatus(userId) {
    return request(`/credentials/${userId}/status`);
}

/* =================== History =================== */

export async function getActionHistory(userId, limit = 50) {
    return request(`/history/${userId}?limit=${limit}`);
}

/**
 * Load chat history for persistent chat view on login.
 * Uses the same audit log endpoint with a higher limit.
 */
export async function getChatHistory(userId, limit = 200) {
    return request(`/history/${userId}?limit=${limit}`);
}

/**
 * Poll for pending playground messages (e.g. reminder deliveries from QStash).
 * The backend pops and returns messages atomically so each is shown exactly once.
 */
export async function getPlaygroundMessages(userId) {
    return request(`/playground/messages/${userId}`);
}
