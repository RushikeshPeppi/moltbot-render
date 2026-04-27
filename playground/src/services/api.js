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
 *
 * `city` is optional but strongly encouraged — it powers the web-search skill's
 * "near me" handling. If the user skips it at signup, the playground will
 * prompt for it on first chat load via CityPromptModal.
 */
export async function createPlaygroundUser(name, redirectUri, timezone = 'UTC', city = null) {
    const body = { name, redirect_uri: redirectUri, timezone };
    if (city) body.city = city;
    return request('/playground/create-user', {
        method: 'POST',
        body: JSON.stringify(body),
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

/**
 * Update a user's city.
 *
 * Used by the city-prompt modal that appears on chat load when the user's
 * city is empty in the database (i.e. existing users created before the
 * city column was added, or users who skipped the field at signup).
 */
export async function updateUserCity(userId, city) {
    return request(`/playground/users/${userId}/city`, {
        method: 'PATCH',
        body: JSON.stringify({ city }),
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

export async function executeAction(userId, message, timezone = 'UTC') {
    return request('/execute-action', {
        method: 'POST',
        body: JSON.stringify({
            user_id: userId,
            message,
            timezone,
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

/* =================== Token Usage =================== */

/**
 * Get token usage data for PM dashboard.
 * @param {Object} filters - { user_id, date_from, date_to, action_type, limit }
 */
export async function getTokenUsage(filters = {}) {
    const params = new URLSearchParams();
    if (filters.user_id) params.set('user_id', filters.user_id);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    if (filters.action_type) params.set('action_type', filters.action_type);
    if (filters.limit) params.set('limit', filters.limit);
    return request(`/playground/token-usage?${params.toString()}`);
}

/**
 * Get CSV download URL for token usage data.
 */
export function getTokenUsageCsvUrl(filters = {}) {
    const params = new URLSearchParams();
    if (filters.user_id) params.set('user_id', filters.user_id);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    if (filters.action_type) params.set('action_type', filters.action_type);
    if (filters.limit) params.set('limit', filters.limit);
    return `${BASE}/playground/token-usage/csv?${params.toString()}`;
}
