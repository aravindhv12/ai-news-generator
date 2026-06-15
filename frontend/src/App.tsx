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

  // Initial load
  useEffect(() => {
    if (token) {
      setLoading(true);
      fetchData().finally(() => setLoading(false));
    }
  }, [token, fetchData]);

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

  // Approve Post: transitions to QUEUED
  const approvePost = async (id: string) => {
    try {
      await api.post('/api/posts/approve', { post_id: id });
      await fetchData();
    } catch (err) {
      alert("Failed to approve post.");
    }
  };

  // Reject Post: transitions to REJECTED and generates replacement
  const rejectPost = async (id: string) => {
    try {
      await api.post('/api/posts/reject', { post_id: id });
      await fetchData();
    } catch (err) {
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
          <h2>AUTO.TECH Secure</h2>
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
          <span>AUTO.TECH</span>
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
          <div className="loading-state">
            <BarChart2 size={48} style={{ color: 'var(--accent)' }} />
            <h3>Analytics Dashboard</h3>
            <p>Publish statistics, audience engagement graphs, and performance tracking metrics are coming soon.</p>
          </div>
        )}

        {view === 'settings' && (
          <div className="loading-state">
            <SettingsIcon size={48} style={{ color: 'var(--text-muted)' }} />
            <h3>Platform Settings</h3>
            <p>Configure API integrations, Vercel cron scheduling, and theme details here.</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
