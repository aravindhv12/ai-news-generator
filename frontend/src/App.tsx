import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { 
  Layout, 
  RefreshCw, 
  BarChart2, 
  Settings as SettingsIcon, 
  Activity, 
  Lock, 
  User, 
  CheckCircle2, 
  AlertCircle, 
  Loader2,
  Clock,
  TrendingUp,
  Send,
  History,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  ArrowRight,
  Plus
} from 'lucide-react';
import './App.css';

interface Post {
  id: string;
  title: string;
  caption: string;
  image_url: string;
  status: string;
  generation_source: string;
  created_at: string;
  approved_at?: string;
  published_at?: string;
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [view, setView] = useState<'dashboard' | 'analytics' | 'settings'>('dashboard');
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [customCount, setCustomCount] = useState<number>(4);
  const [localGenerating, setLocalGenerating] = useState(false);
  const [showTimeoutWarning, setShowTimeoutWarning] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState(60);

  // Dynamic Settings State
  const [settingsForm, setSettingsForm] = useState({
    PROJECT_NAME: '',
    OLLAMA_BASE_URL: '',
    OLLAMA_MODEL: '',
    INSTAGRAM_ACCESS_TOKEN: '',
    INSTAGRAM_BUSINESS_ID: '',
    PUBLIC_HOST: '',
    CRON_SECRET: ''
  });
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState('');

  // Processing state for post actions to prevent double click
  const [processingPostIds, setProcessingPostIds] = useState<string[]>([]);

  // Redesigned dashboard state variables
  const [stats, setStats] = useState({
    total: 0,
    draft: 0,
    approved: 0,
    queued: 0,
    publishing: 0,
    published: 0,
    rejected: 0,
    failed: 0
  });

  const [displays, setDisplays] = useState({
    last_auto_run: null as string | null,
    next_auto_run: null as string | null,
    last_manual_run: null as string | null,
    generated_today: 0,
    published_today: 0
  });

  const [generationHistory, setGenerationHistory] = useState<any[]>([]);
  const [publishingQueue, setPublishingQueue] = useState<any[]>([]);
  const [recentActivity, setRecentActivity] = useState<any[]>([]);

  // Login states
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');

  const apiBaseURL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? 'http://localhost:8000' : '';

  const api = useMemo(() => axios.create({
    baseURL: apiBaseURL,
    headers: { Authorization: `Bearer ${token}` }
  }), [token, apiBaseURL]);

  const loggedInUser = useMemo(() => {
    if (!token) return null;
    try {
      const payloadBase64 = token.split('.')[1];
      const decodedPayload = JSON.parse(atob(payloadBase64));
      return decodedPayload.sub || null;
    } catch (e) {
      console.error("Error decoding token:", e);
      return null;
    }
  }, [token]);

  // Redirect non-admin away from settings
  useEffect(() => {
    if (view === 'settings' && loggedInUser && loggedInUser !== 'admin') {
      setView('dashboard');
    }
  }, [view, loggedInUser]);

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      const [postsResp, dashResp] = await Promise.all([
        api.get('/api/posts'),
        api.get('/api/dashboard')
      ]);
      
      setPosts(postsResp.data);

      const dash = dashResp.data;
      setStats(dash.stats);
      setDisplays(dash.displays);
      setGenerationHistory(dash.generation_history);
      setPublishingQueue(dash.publishing_queue);
      setRecentActivity(dash.recent_activity);
      
      // Auto sync scanning state with backend pipeline status
      if (dash.pipeline.status === 'running') {
        setScanning(true);
      } else {
        setScanning(false);
      }
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) handleLogout();
    }
  }, [token, api]);

  const fetchSettings = useCallback(async () => {
    if (!token) return;
    try {
      const resp = await api.get('/api/settings');
      setSettingsForm(resp.data);
    } catch (err) {
      console.error("Failed to fetch settings:", err);
    }
  }, [token, api]);

  // Analytics States
  const [analyticsData, setAnalyticsData] = useState<any>(null);
  const [sourceStats, setSourceStats] = useState<any>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);

  const fetchAnalytics = useCallback(async () => {
    if (!token) return;
    setLoadingAnalytics(true);
    try {
      const [dashResp, sourcesResp] = await Promise.all([
        api.get('/api/analytics/dashboard'),
        api.get('/api/analytics/sources')
      ]);
      setAnalyticsData(dashResp.data);
      setSourceStats(sourcesResp.data);
    } catch (err) {
      console.error("Failed to fetch analytics:", err);
    } finally {
      setLoadingAnalytics(false);
    }
  }, [token, api]);

  // Initial load
  useEffect(() => {
    if (token) {
      setLoading(true);
      Promise.all([fetchData(), fetchSettings()]).finally(() => setLoading(false));
    }
  }, [token, fetchData, fetchSettings]);

  // Load analytics when switching to the view
  useEffect(() => {
    if (token && view === 'analytics') {
      fetchAnalytics();
    }
  }, [token, view, fetchAnalytics]);

  // Real-time polling every 2 seconds
  useEffect(() => {
    if (!token) return;
    const interval = setInterval(() => {
      fetchData();
    }, 2000);
    return () => clearInterval(interval);
  }, [token, fetchData]);


  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError('');
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);
      const response = await axios.post(`${apiBaseURL}/api/auth/login`, formData);
      localStorage.setItem('token', response.data.access_token);
      setToken(response.data.access_token);
    } catch (err: any) {
      if (err.response) {
        if (err.response.status === 401) {
          setLoginError('Invalid credentials');
        } else {
          const detail = err.response.data?.detail || err.response.data?.message || 'Internal Server Error';
          setLoginError(`Server error (${err.response.status}): ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
        }
      } else if (err.request) {
        setLoginError('Could not connect to backend server. Please verify your database connection variables on Vercel.');
      } else {
        setLoginError('An unexpected error occurred.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setPosts([]);
  };

  // Inactivity tracking: warn at 9m, logout at 10m
  useEffect(() => {
    if (!token) return;

    let warningTimer: any;
    let logoutTimer: any;
    let countdownInterval: any;

    const resetTimers = () => {
      setShowTimeoutWarning(false);
      setTimeRemaining(60);
      
      if (warningTimer) clearTimeout(warningTimer);
      if (logoutTimer) clearTimeout(logoutTimer);
      if (countdownInterval) clearInterval(countdownInterval);

      // Warning after 9 minutes (540 seconds)
      warningTimer = setTimeout(() => {
        setShowTimeoutWarning(true);
        let timeLeft = 60;
        countdownInterval = setInterval(() => {
          timeLeft -= 1;
          setTimeRemaining(timeLeft);
          if (timeLeft <= 0) {
            clearInterval(countdownInterval);
          }
        }, 1000);
      }, 9 * 60 * 1000);

      // Logout after 10 minutes (600 seconds)
      logoutTimer = setTimeout(() => {
        handleLogout();
        alert("You have been logged out due to inactivity.");
      }, 10 * 60 * 1000);
    };

    const events = ['mousemove', 'keydown', 'mousedown', 'scroll', 'touchstart'];
    const handler = () => resetTimers();
    
    events.forEach(event => {
      window.addEventListener(event, handler);
    });

    // Run initially
    resetTimers();

    return () => {
      events.forEach(event => {
        window.removeEventListener(event, handler);
      });
      if (warningTimer) clearTimeout(warningTimer);
      if (logoutTimer) clearTimeout(logoutTimer);
      if (countdownInterval) clearInterval(countdownInterval);
    };
  }, [token]);

  // Trigger manual generation
  const triggerGeneration = async (count: number) => {
    setLocalGenerating(true);
    try {
      await api.post('/api/generate', { count });
      await fetchData();
    } catch (err) {
      alert("Failed to trigger generation. Please check if you are within the 30 seconds rate limit.");
    } finally {
      setLocalGenerating(false);
    }
  };

  // Approve Post: transitions to QUEUED (Optimistic Update with double click protection)
  const approvePost = async (id: string) => {
    if (processingPostIds.includes(id)) return;
    setProcessingPostIds(prev => [...prev, id]);

    const previousPosts = [...posts];
    const previousStats = { ...stats };

    // Update state immediately
    setPosts(prevPosts =>
      prevPosts.map(p => (p.id === id ? { ...p, status: 'QUEUED' } : p))
    );
    setStats(prevStats => ({
      ...prevStats,
      draft: Math.max(0, prevStats.draft - 1),
      queued: prevStats.queued + 1
    }));

    try {
      await api.post('/api/posts/approve', { post_id: id });
      fetchData(); // Silently refresh
    } catch (err) {
      // Rollback on error
      setPosts(previousPosts);
      setStats(previousStats);
      alert("Failed to approve post.");
    } finally {
      setProcessingPostIds(prev => prev.filter(item => item !== id));
    }
  };

  // Reject Post: transitions to REJECTED and generates replacement (Optimistic Update with double click protection)
  const rejectPost = async (id: string) => {
    if (processingPostIds.includes(id)) return;
    setProcessingPostIds(prev => [...prev, id]);

    const previousPosts = [...posts];
    const previousStats = { ...stats };

    // Update state immediately
    setPosts(prevPosts =>
      prevPosts.map(p => (p.id === id ? { ...p, status: 'REJECTED' } : p))
    );
    setStats(prevStats => ({
      ...prevStats,
      draft: Math.max(0, prevStats.draft - 1),
      rejected: prevStats.rejected + 1
    }));

    try {
      await api.post('/api/posts/reject', { post_id: id });
      await fetchData(); // Fetch again since rejection creates a replacement
    } catch (err) {
      // Rollback on error
      setPosts(previousPosts);
      setStats(previousStats);
      alert("Failed to reject post.");
    } finally {
      setProcessingPostIds(prev => prev.filter(item => item !== id));
    }
  };

  // Trigger publish worker immediately
  const triggerPublishWorker = async () => {
    try {
      await api.post('/api/posts/publish');
      await fetchData();
    } catch (err) {
      alert("Failed to trigger publish queue processing.");
    }
  };

  // Save Settings to Backend
  const saveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingSettings(true);
    setSettingsStatus('');
    try {
      await api.post('/api/settings', settingsForm);
      setSettingsStatus('Settings updated successfully!');
      fetchSettings();
    } catch (err) {
      setSettingsStatus('Failed to update settings. Please try again.');
    } finally {
      setSavingSettings(false);
    }
  };


  const formatTime = (isoString: string | null) => {
    if (!isoString) return 'Never';
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' ' + date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  if (!token) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <Activity className="logo-icon pulse" size={48} style={{ color: 'var(--primary)', marginBottom: '1rem' }} />
          <h2>Guess Secure</h2>
          <form onSubmit={handleLogin}>
            <div className="input-group">
              <User size={18} />
              <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
            </div>
            <div className="input-group">
              <Lock size={18} />
              <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
            {loginError && <p className="error-msg">{loginError}</p>}
            <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
              {loading ? <Loader2 className="spin" /> : 'Log In'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard fade-in">
      <aside className="sidebar">
        <div className="logo">
          <Activity size={32} />
          <span>{settingsForm.PROJECT_NAME || 'Guess'}</span>
        </div>
        <nav>
          <button className={`nav-button ${view === 'dashboard' ? 'active' : ''}`} onClick={() => setView('dashboard')}>
            <Layout size={20} /> Dashboard
          </button>
          <button className={`nav-button ${view === 'analytics' ? 'active' : ''}`} onClick={() => setView('analytics')}>
            <BarChart2 size={20} /> Analytics
          </button>
          {loggedInUser === 'admin' && (
            <button className={`nav-button ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>
              <SettingsIcon size={20} /> Settings
            </button>
          )}
        </nav>
        <div className="sidebar-footer">
          <button className="nav-button logout-btn" onClick={handleLogout}>Log Out</button>
        </div>
      </aside>

      <main className="content">
        <header>
          <div>
            <h1 className="slide-up">{view.charAt(0).toUpperCase() + view.slice(1)}</h1>
            <p className="subtitle">Tech Social Card Automation Engine.</p>
          </div>

          {view === 'dashboard' && (
            <div className="header-actions">
              <button className="btn btn-secondary" onClick={fetchData}>
                <RefreshCw className={loading ? 'spin' : ''} size={18} />
              </button>
            </div>
          )}
        </header>

        {view === 'dashboard' && (
          <div className="fade-in">
            {/* Stats Grid */}
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-value" style={{ color: '#fff' }}>{stats.total}</div>
                <div className="stat-label">Total Posts</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: '#d0d0d5' }}>{stats.draft}</div>
                <div className="stat-label">Draft</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: 'var(--accent)' }}>{stats.queued}</div>
                <div className="stat-label">Queued</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: 'var(--warning)' }}>{stats.publishing}</div>
                <div className="stat-label">Publishing</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: 'var(--primary)' }}>{stats.published}</div>
                <div className="stat-label">Published</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: 'var(--error)' }}>{stats.rejected}</div>
                <div className="stat-label">Rejected</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: '#ff6666' }}>{stats.failed}</div>
                <div className="stat-label">Failed</div>
              </div>
            </div>

            {/* Displays Timeline Bar */}
            <div className="displays-bar">
              <div className="display-item">
                <span className="display-title">Last Auto Run</span>
                <span className="display-value">{formatTime(displays.last_auto_run)}</span>
              </div>
              <div className="display-item">
                <span className="display-title">Next Auto Run</span>
                <span className="display-value">{formatTime(displays.next_auto_run)}</span>
              </div>
              <div className="display-item">
                <span className="display-title">Last Manual Run</span>
                <span className="display-value">{formatTime(displays.last_manual_run)}</span>
              </div>
              <div className="display-item">
                <span className="display-title">Generated Today</span>
                <span className="display-value">{displays.generated_today} Posts</span>
              </div>
              <div className="display-item">
                <span className="display-title">Published Today</span>
                <span className="display-value">{displays.published_today} Posts</span>
              </div>
            </div>

            {/* Manual Generation Panel */}
            <div className="control-panel">
              <div className="control-info">
                <h3>Manual Generation Control</h3>
                <p>Generate fresh premium tech post drafts instantly to review and approve.</p>
              </div>
              <div className="control-actions">
                <button className="btn btn-secondary" onClick={() => triggerGeneration(1)} disabled={scanning || localGenerating}>
                  {scanning || localGenerating ? <Loader2 className="spin" size={14} style={{ marginRight: '6px', display: 'inline' }} /> : null}
                  Generate 1 Post
                </button>
                <button className="btn btn-secondary" onClick={() => triggerGeneration(4)} disabled={scanning || localGenerating}>
                  {scanning || localGenerating ? <Loader2 className="spin" size={14} style={{ marginRight: '6px', display: 'inline' }} /> : null}
                  Generate 4 Posts
                </button>
                <div className="custom-range">
                  <span>Count:</span>
                  <input 
                    type="number" 
                    min="1" 
                    max="10" 
                    value={customCount} 
                    onChange={(e) => setCustomCount(Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))} 
                    disabled={scanning || localGenerating}
                  />
                  <button className="btn btn-primary" onClick={() => triggerGeneration(customCount)} disabled={scanning || localGenerating}>
                    {scanning || localGenerating ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
                    {scanning || localGenerating ? 'Generating...' : 'Generate Now'}
                  </button>
                </div>
              </div>
            </div>

            {/* Main Content Areas */}
            {loading && posts.length === 0 ? (
              <div className="loading-state">
                <Loader2 className="spin-large" size={48} />
                <p>Syncing dashboard statistics...</p>
              </div>
            ) : (
              <div>
                <h2>Generated Drafts & Content Review</h2>
                <div className="post-grid">
                  {posts.filter(p => p.status === 'DRAFT').length === 0 ? (
                    <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
                      <AlertCircle size={48} />
                      <p>No draft posts prepared yet. Click "Generate Now" or wait for the scheduler to begin.</p>
                    </div>
                  ) : (
                    posts.filter(p => p.status === 'DRAFT').map(post => (
                      <article key={post.id} className="post-card slide-up">
                        <div className="post-image-container">
                          <img 
                            src={`${apiBaseURL}/output/${post.id}_clean.png`} 
                            alt="Post Preview" 
                            className="preview-img" 
                            onError={(e) => {
                              const target = e.target as HTMLImageElement;
                              if (target.src.includes('_clean.png')) {
                                target.src = `${apiBaseURL}/output/${post.id}.png`;
                              } else if (target.src.includes('.png')) {
                                target.src = post.image_url;
                              }
                            }} 
                          />
                        </div>
                        <div className="post-info">
                          <div className="post-meta-header">
                            <span className={`post-status status-${post.status}`}>{post.status}</span>
                            <span className="post-source">{post.generation_source}</span>
                          </div>
                          <h3 className="post-title">{post.title}</h3>
                          <p className="post-caption">{post.caption}</p>
                          <div className="card-actions">
                            <button 
                              className="btn btn-primary" 
                              onClick={() => approvePost(post.id)} 
                              disabled={processingPostIds.includes(post.id)}
                            >
                              {processingPostIds.includes(post.id) ? (
                                <Loader2 className="spin" size={16} />
                              ) : (
                                <>
                                  <ThumbsUp size={16} /> Approve
                                </>
                              )}
                            </button>
                            <button 
                              className="btn btn-danger" 
                              onClick={() => rejectPost(post.id)} 
                              disabled={processingPostIds.includes(post.id)}
                            >
                              {processingPostIds.includes(post.id) ? (
                                <Loader2 className="spin" size={16} />
                              ) : (
                                <>
                                  <ThumbsDown size={16} /> Reject
                                </>
                              )}
                            </button>
                          </div>

                        </div>
                      </article>
                    ))
                  )}
                </div>

                {/* Dashboard Section Widgets */}
                <div className="dashboard-layout">
                  {/* Section 1: Publishing Queue */}
                  <div className="dashboard-section">
                    <div className="section-header">
                      <h3>Publishing Queue</h3>
                      <button className="btn btn-primary" style={{ padding: '4px 10px', fontSize: '0.75rem' }} onClick={triggerPublishWorker}>
                        <Send size={12} /> Force Publish
                      </button>
                    </div>
                    <div className="section-list">
                      {publishingQueue.length === 0 ? (
                        <div className="empty-state" style={{ height: '80%' }}>
                          <p>Queue is empty.</p>
                        </div>
                      ) : (
                        publishingQueue.map(item => (
                          <div key={item.id} className="list-item">
                            <div className="item-left">
                              <span className="item-title">{item.title}</span>
                              <span className="item-meta">Queued: {formatTime(item.queued_at)}</span>
                            </div>
                            <div className="item-right">
                              <span className={`post-status status-${item.status.toUpperCase()}`} style={{ fontSize: '0.65rem' }}>
                                {item.status}
                              </span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Section 2: Generation History */}
                  <div className="dashboard-section">
                    <div className="section-header">
                      <h3>Generation History</h3>
                      <History size={16} style={{ color: 'var(--text-muted)' }} />
                    </div>
                    <div className="section-list">
                      {generationHistory.length === 0 ? (
                        <div className="empty-state" style={{ height: '80%' }}>
                          <p>No generation history.</p>
                        </div>
                      ) : (
                        generationHistory.map(run => (
                          <div key={run.id} className="list-item">
                            <div className="item-left">
                              <span className="item-title">{run.source} RUN</span>
                              <span className="item-meta">Start: {formatTime(run.started_at)}</span>
                            </div>
                            <div className="item-right">
                              <span style={{ fontSize: '0.75rem', color: 'var(--primary)', fontWeight: 'bold' }}>
                                +{run.generated_count} posts
                              </span>
                              <div className="item-meta" style={{ fontSize: '0.65rem' }}>{run.status}</div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Section 3: Recent Activity */}
                  <div className="dashboard-section">
                    <div className="section-header">
                      <h3>Recent Activity</h3>
                      <Activity size={16} style={{ color: 'var(--text-muted)' }} />
                    </div>
                    <div className="section-list">
                      {recentActivity.length === 0 ? (
                        <div className="empty-state" style={{ height: '80%' }}>
                          <p>No recent activity.</p>
                        </div>
                      ) : (
                        recentActivity.map(act => (
                          <div key={act.id} className="list-item">
                            <div className="item-left">
                              <span className="item-title" style={{ textTransform: 'capitalize' }}>
                                {act.action.replace('_', ' ')}
                              </span>
                              <span className="item-meta">Entity: {act.entity_type}</span>
                            </div>
                            <div className="item-right">
                              <span className="item-meta">{formatTime(act.created_at)}</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {view === 'analytics' && (
          <div className="fade-in">
            <header>
              <div>
                <h2>Analytics Dashboard</h2>
                <p className="subtitle">Real-time publishing insights and database distribution metrics</p>
              </div>
              <button className="btn btn-secondary" onClick={fetchAnalytics} disabled={loadingAnalytics}>
                <RefreshCw className={loadingAnalytics ? "spin" : ""} size={16} /> Refresh
              </button>
            </header>

            {loadingAnalytics && !analyticsData ? (
              <div className="loading-state">
                <Loader2 className="spin-large" size={32} />
                <p>Loading platform metrics...</p>
              </div>
            ) : analyticsData ? (
              <div className="slide-up">
                {/* Metrics Grid */}
                <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)', marginBottom: '2rem' }}>
                  <div className="stat-card" style={{ borderColor: 'var(--primary)', background: 'rgba(0, 255, 127, 0.02)' }}>
                    <div className="stat-value" style={{ color: 'var(--primary)' }}>{analyticsData.success_rate}%</div>
                    <div className="stat-label">Success Rate</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{analyticsData.total_news}</div>
                    <div className="stat-label">News Collected</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{analyticsData.total_posts}</div>
                    <div className="stat-label">Posts Generated</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value" style={{ color: 'var(--accent)' }}>{analyticsData.published_posts}</div>
                    <div className="stat-label">Published Posts</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value" style={{ color: 'var(--warning)' }}>{analyticsData.pending_approval}</div>
                    <div className="stat-label">Pending Approval</div>
                  </div>
                </div>

                {/* Sources & Performance Section */}
                <div className="dashboard-layout" style={{ gridTemplateColumns: '2fr 1fr' }}>
                  {/* Sources Card */}
                  <div className="dashboard-section" style={{ height: 'auto', minHeight: '350px' }}>
                    <div className="section-header">
                      <h3>News Sources Distribution</h3>
                      <TrendingUp size={16} style={{ color: 'var(--primary)' }} />
                    </div>
                    <div className="section-list" style={{ padding: '0.5rem 0' }}>
                      {sourceStats && Object.keys(sourceStats).length > 0 ? (
                        Object.entries(sourceStats).map(([source, count]: [string, any]) => {
                          const total = Object.values(sourceStats).reduce((a: any, b: any) => a + b, 0) as number;
                          const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                          return (
                            <div key={source} style={{ marginBottom: '1.2rem' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '6px', fontWeight: 600 }}>
                                <span>{source}</span>
                                <span style={{ color: 'var(--text-muted)' }}>{count} articles ({pct}%)</span>
                              </div>
                              <div style={{ width: '100%', height: '8px', background: '#1c1c22', borderRadius: '4px', overflow: 'hidden' }}>
                                <div style={{ height: '100%', width: `${pct}%`, background: 'linear-gradient(90deg, var(--accent) 0%, var(--primary) 100%)', borderRadius: '4px' }} />
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div className="empty-state">
                          <p>No source data available.</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* System Insights Card */}
                  <div className="dashboard-section" style={{ height: 'auto', minHeight: '350px' }}>
                    <div className="section-header">
                      <h3>Pluggable Insights</h3>
                      <Sparkles size={16} style={{ color: 'var(--warning)' }} />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem', justifyContent: 'center', height: '100%', padding: '0.5rem' }}>
                      <div className="list-item" style={{ border: 'none', padding: 0 }}>
                        <div className="item-left">
                          <span className="item-title" style={{ color: 'var(--primary)' }}>AI Credit Efficiency</span>
                          <span className="item-meta" style={{ fontSize: '0.8rem' }}>Batch generation saved ~{displays.generated_today * 3} API credits today.</span>
                        </div>
                      </div>
                      <div className="list-item" style={{ border: 'none', padding: 0 }}>
                        <div className="item-left">
                          <span className="item-title" style={{ color: 'var(--accent)' }}>Publishing Queue Status</span>
                          <span className="item-meta" style={{ fontSize: '0.8rem' }}>Next auto-publish run will process {stats.queued} queued posts.</span>
                        </div>
                      </div>
                      <div className="list-item" style={{ border: 'none', padding: 0 }}>
                        <div className="item-left">
                          <span className="item-title" style={{ color: '#fff' }}>Database Health</span>
                          <span className="item-meta" style={{ fontSize: '0.8rem' }}>E2E cleanup runs nightly to optimize SQLite/Postgres indexes.</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="loading-state">
                <BarChart2 size={48} style={{ color: 'var(--accent)' }} />
                <p>Click Refresh to load metrics.</p>
              </div>
            )}
          </div>
        )}

        {view === 'settings' && (
          <div className="fade-in">
            <header>
              <div>
                <h2>Platform Settings</h2>
                <p className="subtitle">Configure brand rules, secrets integration, and background worker engines</p>
              </div>
            </header>

            <form onSubmit={saveSettings} className="slide-up" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              {/* Settings Card 1: Platform & Rebranding */}
              <div className="dashboard-section" style={{ height: 'auto' }}>
                <div className="section-header">
                  <h3>Brand & Styling Configuration</h3>
                  <Sparkles size={16} style={{ color: 'var(--primary)' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem', padding: '0.5rem 0' }}>
                  <div className="settings-row">
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Active Brand Identifier</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Registered name for Navbar, Sidebar, and card overlay assets</div>
                    </div>
                    <input 
                      type="text" 
                      className="settings-input" 
                      value={settingsForm.PROJECT_NAME} 
                      onChange={e => setSettingsForm({...settingsForm, PROJECT_NAME: e.target.value})} 
                      required 
                    />
                  </div>
                  <div className="settings-row">
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Public Hostname URL</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Used as base for Instagram post webhook images</div>
                    </div>
                    <input 
                      type="text" 
                      className="settings-input" 
                      value={settingsForm.PUBLIC_HOST} 
                      onChange={e => setSettingsForm({...settingsForm, PUBLIC_HOST: e.target.value})} 
                      required 
                    />
                  </div>
                </div>
              </div>

              {/* Settings Card 2: AI Engine Configuration */}
              <div className="dashboard-section" style={{ height: 'auto' }}>
                <div className="section-header">
                  <h3>AI Content Generator Configuration</h3>
                  <Sparkles size={16} style={{ color: 'var(--warning)' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem', padding: '0.5rem 0' }}>
                  <div className="settings-row">
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Ollama Base URL</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Target address of the offline Ollama service (default: localhost:11434)</div>
                    </div>
                    <input 
                      type="text" 
                      className="settings-input" 
                      value={settingsForm.OLLAMA_BASE_URL} 
                      onChange={e => setSettingsForm({...settingsForm, OLLAMA_BASE_URL: e.target.value})} 
                      required 
                    />
                  </div>
                  <div className="settings-row">
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Ollama Model Name</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Large language model identifier loaded on Ollama service</div>
                    </div>
                    <input 
                      type="text" 
                      className="settings-input" 
                      value={settingsForm.OLLAMA_MODEL} 
                      onChange={e => setSettingsForm({...settingsForm, OLLAMA_MODEL: e.target.value})} 
                      required 
                    />
                  </div>
                </div>
              </div>

              {/* Settings Card 3: Secrets & Environment Integration */}
              <div className="dashboard-section" style={{ height: 'auto' }}>
                <div className="section-header">
                  <h3>Secrets & Environment Integration</h3>
                  <Lock size={16} style={{ color: 'var(--accent)' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem', padding: '0.5rem 0' }}>
                  <div className="settings-row">
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Instagram Access Token</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Bearer API token granted by Meta Developers console</div>
                    </div>
                    <input 
                      type="password" 
                      className="settings-input" 
                      placeholder="••••••••••••••••" 
                      value={settingsForm.INSTAGRAM_ACCESS_TOKEN} 
                      onChange={e => setSettingsForm({...settingsForm, INSTAGRAM_ACCESS_TOKEN: e.target.value})} 
                    />
                  </div>
                  <div className="settings-row">
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Instagram Business ID</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Unique Meta business account identifier linking to Instagram page</div>
                    </div>
                    <input 
                      type="text" 
                      className="settings-input" 
                      value={settingsForm.INSTAGRAM_BUSINESS_ID} 
                      onChange={e => setSettingsForm({...settingsForm, INSTAGRAM_BUSINESS_ID: e.target.value})} 
                    />
                  </div>
                  <div className="settings-row">
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Vercel Cron Secret</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Security validation string authorizing Vercel daily automation requests</div>
                    </div>
                    <input 
                      type="password" 
                      className="settings-input" 
                      placeholder="••••••••••••••••" 
                      value={settingsForm.CRON_SECRET} 
                      onChange={e => setSettingsForm({...settingsForm, CRON_SECRET: e.target.value})} 
                    />
                  </div>
                </div>
              </div>

              {settingsStatus && (
                <div style={{ 
                  padding: '1rem', 
                  borderRadius: '12px', 
                  backgroundColor: settingsStatus.includes('successfully') ? 'rgba(52, 199, 89, 0.1)' : 'rgba(255, 59, 48, 0.1)',
                  color: settingsStatus.includes('successfully') ? 'var(--success)' : 'var(--error)',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  {settingsStatus.includes('successfully') ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
                  {settingsStatus}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
                <button type="submit" className="btn btn-primary" disabled={savingSettings} style={{ width: '180px' }}>
                  {savingSettings ? <Loader2 className="spin" size={16} /> : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        )}
      </main>
      {showTimeoutWarning && (
        <div className="modal-overlay">
          <div className="modal-content warning-modal">
            <Clock className="warning-icon pulse" size={48} style={{ color: 'var(--warning)', marginBottom: '1rem' }} />
            <h2>Session Timeout Warning</h2>
            <p>You have been inactive. For your security, you will be logged out in <strong>{timeRemaining}</strong> seconds.</p>
            <p>Move your mouse or press any key to stay logged in.</p>
            <button className="btn btn-primary" onClick={() => setShowTimeoutWarning(false)}>
              Keep Me Logged In
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
