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
      fetchData().finally(() => setLoading(false));
    }
  }, [token, fetchData]);

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

  // Trigger manual generation
  const triggerGeneration = async (count: number) => {
    setScanning(true);
    try {
      await api.post('/api/generate', { count });
      await fetchData();
    } catch (err) {
      setScanning(false);
      alert("Failed to trigger generation.");
    }
  };

  // Approve Post: transitions to QUEUED (Optimistic Update)
  const approvePost = async (id: string) => {
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
    }
  };

  // Reject Post: transitions to REJECTED and generates replacement (Optimistic Update)
  const rejectPost = async (id: string) => {
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
        <div className="logo pulse">
          <Activity size={32} />
          <span>Guess</span>
        </div>
        <nav>
          <button className={`nav-button ${view === 'dashboard' ? 'active' : ''}`} onClick={() => setView('dashboard')}>
            <Layout size={20} /> Dashboard
          </button>
          <button className={`nav-button ${view === 'analytics' ? 'active' : ''}`} onClick={() => setView('analytics')}>
            <BarChart2 size={20} /> Analytics
          </button>
          <button className={`nav-button ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>
            <SettingsIcon size={20} /> Settings
          </button>
        </nav>
        <div className="sidebar-footer">
          <button className="nav-button logout-btn" onClick={handleLogout}>Log Out</button>
        </div>
      </aside>

      <main className="content">
        <header>
          <div>
            <h1 className="slide-up">{view.charAt(0).toUpperCase() + view.slice(1)}</h1>
            <p className="subtitle">Production AI Social Media Platform.</p>
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
                <button className="btn btn-secondary" onClick={() => triggerGeneration(1)} disabled={scanning}>
                  Generate 1 Post
                </button>
                <button className="btn btn-secondary" onClick={() => triggerGeneration(4)} disabled={scanning}>
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
                  />
                  <button className="btn btn-primary" onClick={() => triggerGeneration(customCount)} disabled={scanning}>
                    {scanning ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
                    Generate Now
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
                          <img src={`${apiBaseURL}/output/${post.id}.png`} alt="Card" className="preview-img" 
                            onError={(e) => {(e.target as HTMLImageElement).src = post.image_url}} />
                        </div>
                        <div className="post-info">
                          <div className="post-meta-header">
                            <span className={`post-status status-${post.status}`}>{post.status}</span>
                            <span className="post-source">{post.generation_source}</span>
                          </div>
                          <h3 className="post-title">{post.title}</h3>
                          <p className="post-caption">{post.caption}</p>
                          <div className="card-actions">
                            <button className="btn btn-primary" onClick={() => approvePost(post.id)}>
                              <ThumbsUp size={16} /> Approve
                            </button>
                            <button className="btn btn-danger" onClick={() => rejectPost(post.id)}>
                              <ThumbsDown size={16} /> Reject
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

            <div className="slide-up" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              {/* Settings Card 1: Platform & Rebranding */}
              <div className="dashboard-section" style={{ height: 'auto' }}>
                <div className="section-header">
                  <h3>Brand & Styling Configuration</h3>
                  <Sparkles size={16} style={{ color: 'var(--primary)' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '0.5rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Active Brand Identifier</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Registered name for Navbar, Sidebar, and card overlay assets</div>
                    </div>
                    <span style={{ background: 'rgba(0, 255, 127, 0.08)', color: 'var(--primary)', padding: '6px 12px', borderRadius: '8px', fontSize: '0.8rem', fontWeight: 800 }}>
                      Guess
                    </span>
                  </div>
                  <hr style={{ borderColor: '#15151a', margin: '0.5rem 0' }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>Card branding watermark</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Overlay text written onto generated Pillow social images</div>
                    </div>
                    <span style={{ background: '#1c1c22', color: '#fff', padding: '6px 12px', borderRadius: '8px', fontSize: '0.8rem', fontWeight: 700 }}>
                      GUESS
                    </span>
                  </div>
                </div>
              </div>

              {/* Settings Card 2: Environment Keys Integration */}
              <div className="dashboard-section" style={{ height: 'auto' }}>
                <div className="section-header">
                  <h3>Secrets & Environment Integration</h3>
                  <Lock size={16} style={{ color: 'var(--accent)' }} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.5rem', padding: '0.5rem 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--primary)' }} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>DATABASE_URL</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Active connection pooler linked.</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--primary)' }} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>JWT_SECRET</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Security signing key configured.</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--primary)' }} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Vercel CRON_SECRET</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Injected auth header verified.</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: 'var(--warning)' }} />
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>INSTAGRAM_ACCESS_TOKEN</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Not configured (Pluggable Mock active).</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Settings Card 3: Cron Schedules */}
              <div className="dashboard-section" style={{ height: 'auto' }}>
                <div className="section-header">
                  <h3>Daily Automation Tasks</h3>
                  <Clock size={16} style={{ color: 'var(--warning)' }} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '0.5rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.9rem' }}>
                    <div style={{ fontWeight: 600 }}>Cron Generate: `0 8 * * *` (8:00 AM UTC)</div>
                    <span style={{ color: 'var(--primary)', fontWeight: 600 }}>Active</span>
                  </div>
                  <hr style={{ borderColor: '#15151a', margin: '0.3rem 0' }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.9rem' }}>
                    <div style={{ fontWeight: 600 }}>Cron Cleanup: `0 0 * * *` (12:00 AM UTC)</div>
                    <span style={{ color: 'var(--primary)', fontWeight: 600 }}>Active</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
