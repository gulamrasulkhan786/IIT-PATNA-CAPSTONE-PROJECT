import { useCallback, useContext, useEffect, useMemo, useRef, useState, createContext } from "react";
import "@/App.css";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { jsPDF } from "jspdf";
import html2canvas from "html2canvas";
import {
  BarChart3,
  ClipboardList,
  FileUp,
  History,
  Home,
  Info,
  LogIn,
  LogOut,
  Shield,
  UserPlus,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API_BASE = process.env.REACT_APP_BACKEND_URL
  ? process.env.REACT_APP_BACKEND_URL.replace(/\/$/, "") + "/api"
  : "https://awarness-data-anylasis.onrender.com/api";

console.log("API_BASE:", API_BASE);

const api = axios.create({
  baseURL: API_BASE
});

const USER_TOKEN_KEY = "community_user_token";
const USER_PROFILE_KEY = "community_user_profile";
const ADMIN_TOKEN_KEY = "community_admin_token";
const ADMIN_USER_KEY = "community_admin_username";

const ISSUE_OPTIONS = [
  "Women Safety",
  "Environment",
  "Health",
  "Education",
  "Sanitation",
  "Water",
  "Employment",
  "Crime",
  "Child Welfare",
];

const CHART_COLORS = ["#0F172A", "#C2410C", "#10B981", "#F59E0B", "#6366F1", "#0EA5E9"];

const authHeader = (token) => ({ headers: { Authorization: `Bearer ${token}` } });

const AuthContext = createContext(null);

const useAuth = () => useContext(AuthContext);

const formatDate = (isoDate) => {
  try {
    return new Date(isoDate).toLocaleString();
  } catch {
    return isoDate;
  }
};

const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

const AuthProvider = ({ children }) => {
  const [userToken, setUserToken] = useState(() => {
  return localStorage.getItem(USER_TOKEN_KEY) || null;
});
  const [user, setUser] = useState(() => {
  try {
    const cached = localStorage.getItem(USER_PROFILE_KEY);

    if (!cached || cached === "undefined") return null;

    return JSON.parse(cached);
  } catch (e) {
    console.error("Invalid user data in localStorage:", e);
    return null;
  }
});
  const [adminToken, setAdminToken] = useState(localStorage.getItem(ADMIN_TOKEN_KEY));
  const [adminUsername, setAdminUsername] = useState(localStorage.getItem(ADMIN_USER_KEY));

  const saveUserSession = useCallback((token, profile) => {
    localStorage.setItem(USER_TOKEN_KEY, token);
    localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(profile));
    setUserToken(token);
    setUser(profile);
  }, []);

  const clearUserSession = useCallback(() => {
    localStorage.removeItem(USER_TOKEN_KEY);
    localStorage.removeItem(USER_PROFILE_KEY);
    setUserToken(null);
    setUser(null);
  }, []);

  const saveAdminSession = useCallback((token, username) => {
    localStorage.setItem(ADMIN_TOKEN_KEY, token);
    localStorage.setItem(ADMIN_USER_KEY, username);
    setAdminToken(token);
    setAdminUsername(username);
  }, []);

  const clearAdminSession = useCallback(() => {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    localStorage.removeItem(ADMIN_USER_KEY);
    setAdminToken(null);
    setAdminUsername(null);
  }, []);

  const register = useCallback(
    async (payload) => {
      const response = await api.post("/auth/register", payload);
      saveUserSession(response.data.token, response.data.user);
      return response.data.user;
    },
    [saveUserSession],
  );

  const login = useCallback(
    async (payload) => {
      const response = await api.post("/auth/login", payload);
      saveUserSession(response.data.token, response.data.user);
      return response.data.user;
    },
    [saveUserSession],
  );

  const adminLogin = useCallback(
    async (payload) => {
      const response = await api.post("/admin/login", payload);
      saveAdminSession(response.data.token, response.data.username);
      return response.data.username;
    },
    [saveAdminSession],
  );

  const refreshProfile = useCallback(async () => {
    if (!userToken) {
      return;
    }
    try {
      const response = await api.get("/auth/me", authHeader(userToken));
      localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(response.data));
      setUser(response.data);
    } catch {
      clearUserSession();
    }
  }, [clearUserSession, userToken]);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  const value = useMemo(
    () => ({
      userToken,
      user,
      adminToken,
      adminUsername,
      register,
      login,
      logout: clearUserSession,
      adminLogin,
      adminLogout: clearAdminSession,
    }),
    [
      adminToken,
      adminUsername,
      clearAdminSession,
      clearUserSession,
      login,
      register,
      user,
      userToken,
      adminLogin,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

const ProtectedRoute = ({ children }) => {
  const { userToken } = useAuth();
  if (!userToken) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

const AdminRoute = ({ children }) => {
  const { adminToken } = useAuth();
  if (!adminToken) {
    return <Navigate to="/admin/login" replace />;
  }
  return children;
};

const AppLayout = ({ children }) => {
  const location = useLocation();
  const { user, logout, userToken, adminToken, adminLogout } = useAuth();
  const navigate = useNavigate();

  const userLinks = [
    { to: "/", label: "Home", icon: Home },
    { to: "/manual-entry", label: "Manual Data Entry", icon: ClipboardList },
    { to: "/text-input", label: "Text Input", icon: BarChart3 },
    { to: "/file-upload", label: "File Upload", icon: FileUp },
    { to: "/community-form", label: "Community Form", icon: Users },
    { to: "/history", label: "My History", icon: History },
    { to: "/about", label: "About", icon: Info },
  ];

  return (
    <div className="min-h-screen bg-[var(--app-bg)] text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-200/90 bg-white/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3" data-testid="site-branding">
            <div className="rounded-lg bg-slate-900 p-2 text-white">
              <BarChart3 size={18} />
            </div>
            <div>
              <p className="font-heading text-base font-extrabold tracking-tight">Social Impact Observatory</p>
              <p className="text-xs text-slate-500" data-testid="site-tagline">Community awareness research analytics</p>
            </div>
          </div>
          <nav className="flex flex-wrap items-center gap-2" data-testid="top-navigation-links">
            {userLinks.map((item) => {
              const Icon = item.icon;
              const active = location.pathname === item.to;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  data-testid={`nav-link-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                  className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                    active ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <Icon size={14} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="flex flex-wrap items-center gap-2">
            {!userToken ? (
              <>
                <Link to="/login" data-testid="header-login-link" className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">
                  <LogIn size={14} />
                  Login
                </Link>
                <Link to="/register" data-testid="header-register-link" className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-2 text-sm text-white hover:bg-slate-800">
                  <UserPlus size={14} />
                  Register
                </Link>
              </>
            ) : (
              <>
                <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700" data-testid="header-logged-in-user-email">
                  {user?.email || "Signed in"}
                </div>
                <Button
                  data-testid="header-user-logout-button"
                  variant="outline"
                  onClick={() => {
                    logout();
                    navigate("/login");
                  }}
                >
                  <LogOut size={14} />
                  Logout
                </Button>
              </>
            )}
            {adminToken ? (
              <Button
                data-testid="header-admin-logout-button"
                variant="outline"
                onClick={() => {
                  adminLogout();
                  navigate("/admin/login");
                }}
              >
                <Shield size={14} />
                Admin: Logout
              </Button>
            ) : (
              <Link
                to="/admin/login"
                data-testid="header-admin-login-link"
                className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                <Shield size={14} />
                Admin Login
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
};

const HomePage = () => {
  const { userToken } = useAuth();
  return (
    <div className="space-y-10" data-testid="home-page">
      <section className="grid items-center gap-8 lg:grid-cols-2">
        <div className="space-y-6">
          <p className="inline-flex rounded-full border border-slate-200 bg-white px-3 py-1 text-xs uppercase tracking-wider text-slate-500" data-testid="home-hero-badge">
            Data-first awareness research platform
          </p>
          <h1 className="font-heading text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl" data-testid="home-hero-title">
            Decode Community Patterns With Clear, Independent Analysis
          </h1>
          <p className="max-w-xl text-sm text-slate-600 sm:text-base" data-testid="home-hero-description">
            Collect issue data, compare before/after awareness phases, and generate chart-based insights. Each user sees only their own analysis history.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              to={userToken ? "/manual-entry" : "/register"}
              data-testid="home-start-analysis-button"
              className="inline-flex items-center rounded-md bg-slate-900 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-slate-800"
            >
              Start Analysis
            </Link>
            <Link
              to="/about"
              data-testid="home-learn-more-button"
              className="inline-flex items-center rounded-md border border-slate-300 bg-white px-5 py-3 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50"
            >
              Learn More
            </Link>
          </div>
        </div>
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-3">
          <img
            data-testid="home-hero-image"
            src="https://images.unsplash.com/photo-1758270705317-3ef6142d306f?crop=entropy&cs=srgb&fm=jpg&q=85"
            alt="Community analytics visual"
            className="aspect-[4/3] w-full rounded-xl object-cover"
          />
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3" data-testid="home-feature-grid">
        {[
          "Independent user-specific dataset processing",
          "Inline charts below every analysis input section",
          "Automatic insight and downloadable reports",
        ].map((feature, index) => (
          <Card key={feature} className="border border-slate-200 shadow-sm transition-transform duration-300 hover:-translate-y-1" data-testid={`home-feature-card-${index}`}>
            <CardHeader>
              <CardTitle className="font-heading text-lg">Feature {index + 1}</CardTitle>
              <CardDescription className="text-slate-600">{feature}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>
    </div>
  );
};

const AboutPage = () => (
  <div className="space-y-6" data-testid="about-page">
    <h1 className="font-heading text-4xl font-extrabold tracking-tight text-slate-900" data-testid="about-title">About This Platform</h1>
    <Card className="border border-slate-200 shadow-sm">
      <CardContent className="space-y-4 pt-6">
        <p className="text-sm text-slate-700 sm:text-base" data-testid="about-purpose-text">
          This platform collects community issue data and performs awareness-impact analytics. It does not solve social problems directly. It supports research by presenting patterns through structured tables, charts, and concise insights.
        </p>
        <p className="text-sm text-slate-700 sm:text-base" data-testid="about-privacy-text">
          Every user analysis is isolated. Only admin users can access global submissions and uploaded datasets.
        </p>
      </CardContent>
    </Card>
  </div>
);

const LoginPage = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      await login({ email, password });
      toast.success("Login successful");
      navigate("/manual-entry");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg" data-testid="login-page">
      <Card className="border border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle className="font-heading text-2xl">User Login</CardTitle>
          <CardDescription>Login to access private analysis tools and history.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit} data-testid="login-form">
            <div className="space-y-2">
              <label className="text-sm text-slate-700" htmlFor="login-email">Email</label>
              <Input
                id="login-email"
                data-testid="login-email-input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-slate-700" htmlFor="login-password">Password</label>
              <Input
                id="login-password"
                data-testid="login-password-input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            <Button
              data-testid="login-submit-button"
              type="submit"
              className="w-full bg-slate-900 text-white hover:bg-slate-800"
              disabled={loading}
            >
              {loading ? "Signing in..." : "Login"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

const RegisterPage = () => {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      await register(form);
      toast.success("Registration completed");
      navigate("/manual-entry");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg" data-testid="register-page">
      <Card className="border border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle className="font-heading text-2xl">Create Account</CardTitle>
          <CardDescription>Register with email and password to access all features.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit} data-testid="register-form">
            <div className="space-y-2">
              <label className="text-sm text-slate-700" htmlFor="register-name">Full Name</label>
              <Input
                id="register-name"
                data-testid="register-full-name-input"
                value={form.full_name}
                onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-slate-700" htmlFor="register-email">Email</label>
              <Input
                id="register-email"
                data-testid="register-email-input"
                type="email"
                value={form.email}
                onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-slate-700" htmlFor="register-password">Password</label>
              <Input
                id="register-password"
                data-testid="register-password-input"
                type="password"
                value={form.password}
                onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                minLength={6}
                required
              />
            </div>
            <Button
              data-testid="register-submit-button"
              type="submit"
              className="w-full bg-slate-900 text-white hover:bg-slate-800"
              disabled={loading}
            >
              {loading ? "Creating account..." : "Register"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

const captureNodeAsImage = async (node) => {
  const canvas = await html2canvas(node, {
  scale: 3,
  useCORS: true,
  backgroundColor: "#ffffff",
  logging: false,
  windowWidth: document.body.scrollWidth,
  windowHeight: document.body.scrollHeight
});
  return canvas.toDataURL("image/png");
};

const downloadSectionPdf = async (node, filename) => {
  if (!node) {
    return;
  }
  const image = await captureNodeAsImage(node);
  const pdf = new jsPDF("p", "mm", "a4");
  const width = pdf.internal.pageSize.getWidth() - 20;
  const props = pdf.getImageProperties(image);
  const height = (props.height * width) / props.width;
  pdf.addImage(image, "PNG", 10, 10, width, height);
  pdf.save(filename);
};

const toShortLabel = (value) => {
  const text = String(value || "");
  if (text.length <= 14) {
    return text;
  }
  return `${text.slice(0, 14)}…`;
};

const getChartPayload = (analysis) => {
  const chartData = analysis?.chart_data || {};

  const pieData = chartData.pie_data || chartData.issue_distribution || [];
  const barData = chartData.bar_data
    || (chartData.area_comparison || []).map((item) => ({ label: item.area, count: item.count }));
  const lineData = chartData.line_data || [];
  console.log("LINE DATA:", lineData);
  const lineMode = chartData.line_mode || (chartData.has_awareness_data ? "awareness" : "single");
  const tableRows = chartData.table_rows || analysis?.rows || [];
  const phaseTables = chartData.phase_tables || { before: [], after: [], unphased: [] };

  return {
    pieData,
    barData,
    lineData,
    lineMode,
    tableRows,
    phaseTables,
    hasAwarenessData: Boolean(chartData.has_awareness_data),
    pieTitle: chartData.pie_title || "Issue Distribution (Pie)",
    barTitle: chartData.bar_title || "Area Comparison (Bar)",
    lineTitle: chartData.line_title || (lineMode === "awareness" ? "Before vs After Awareness (Line)" : "Trend (Line)"),
    focusMode: chartData.focus_mode || "mixed",
  };
};

const ChartCanvas = ({ testId, className = "h-72", children }) => {
  const containerRef = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return undefined;
    }

    const updateSize = () => {
      const rect = element.getBoundingClientRect();
      setSize({
        width: Math.max(Math.floor(rect.width), 1),
        height: Math.max(Math.floor(rect.height), 1),
      });
    };

    updateSize();

    let resizeObserver;
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(() => updateSize());
      resizeObserver.observe(element);
    }

    window.addEventListener("resize", updateSize);
    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener("resize", updateSize);
    };
  }, []);

  return (
    <div ref={containerRef} className={className} data-testid={testId}>
      {size.width > 1 && size.height > 1 ? children(size) : null}
    </div>
  );
};

const ResultsPanel = ({ analysis, sectionLabel }) => {
  const tableRef = useRef(null);
  const pieRef = useRef(null);
  const barRef = useRef(null);
  const lineRef = useRef(null);
  const insightRef = useRef(null);

  if (!analysis) {
    return null;
  }

  const {
    pieData,
    barData,
    lineData,
    lineMode,
    tableRows,
    phaseTables,
    hasAwarenessData,
    pieTitle,
    barTitle,
    lineTitle,
    focusMode,
  } = getChartPayload(analysis);

  const awarenessDisplay = hasAwarenessData
    ? `${analysis.summary?.awareness_change_percent ?? 0}%`
    : "N/A";
  const hasPhaseSplitTables = (phaseTables.before?.length || 0) > 0 || (phaseTables.after?.length || 0) > 0;

  const renderStructuredTable = (rows, title, testIdPrefix) => (
    <div className="space-y-3" data-testid={`${testIdPrefix}-section`}>
      <h3 className="font-heading text-lg font-semibold text-slate-900" data-testid={`${testIdPrefix}-title`}>{title}</h3>
      <Table data-testid={`${testIdPrefix}-table`}>
        <TableHeader>
          <TableRow>
            <TableHead className="uppercase tracking-wider">Area</TableHead>
            <TableHead className="uppercase tracking-wider">Issue</TableHead>
            <TableHead className="uppercase tracking-wider">Phase</TableHead>
            <TableHead className="uppercase tracking-wider">Count</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={`${testIdPrefix}-${row.area}-${row.issue}-${index}`} data-testid={`${testIdPrefix}-row-${index}`}>
              <TableCell className="whitespace-normal break-words">{row.area}</TableCell>
              <TableCell className="whitespace-normal break-words">{row.issue}</TableCell>
              <TableCell className="whitespace-normal break-words">{row.phase || "N/A"}</TableCell>
              <TableCell className="font-mono" data-testid={`${testIdPrefix}-count-${index}`}>{row.count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );

  const downloadCombined = async () => {
    const sections = [
      { node: tableRef.current, title: "Structured Table" },
      { node: pieRef.current, title: pieTitle },
      { node: barRef.current, title: barTitle },
      { node: lineRef.current, title: lineTitle },
      { node: insightRef.current, title: "Insight" },
    ].filter((section) => section.node);

    const pdf = new jsPDF("p", "mm", "a4");
    await new Promise(resolve => setTimeout(resolve, 700));
    const pageHeight = pdf.internal.pageSize.getHeight();
    let y = 14;
    const summaryElement = document.getElementById("summary-section");

if (summaryElement) {
  const canvas = await html2canvas(summaryElement, {
  scale: 3,
  useCORS: true,
  backgroundColor: "#ffffff",
  logging: false
});
  const imgData = canvas.toDataURL("image/png");

  const imgWidth = 190;
  const imgHeight = (canvas.height * imgWidth) / canvas.width;


  if (y + imgHeight > pageHeight) {
    pdf.addPage();
    y = 14;
  }

  pdf.setFontSize(14);
  pdf.text("Summary", 10, y);
  y += 6;

  pdf.addImage(imgData, "PNG", 10, y, imgWidth, imgHeight);
  y += imgHeight + 12;
}

    for (let index = 0; index < sections.length; index += 1) {
      const section = sections[index];
      await new Promise(resolve => setTimeout(resolve, 1000));
      const image = await captureNodeAsImage(section.node);
      const width = pdf.internal.pageSize.getWidth() - 20;
      const props = pdf.getImageProperties(image);
      const height = (props.height * width) / props.width;    

      if (y + height + 12 > pageHeight) {
        pdf.addPage();
        y = 14;
      }

      pdf.setFontSize(11);
      pdf.text(section.title, 10, y);
      y += 4;
      pdf.addImage(image, "PNG", 10, y, width, height);
      y += height + 8;
    }

    pdf.save(`${sectionLabel.replace(/\s+/g, "-").toLowerCase()}-combined-report.pdf`);
  };

  return (
    <div className="space-y-6" data-testid={`${sectionLabel.toLowerCase().replace(/\s+/g, "-")}-results-panel`}>
      <Card id="summary-section" className="border border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle className="font-heading text-xl" data-testid="analysis-summary-heading">Summary</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="summary-total-count-card">
            <p className="text-xs uppercase tracking-wide text-slate-500">Total Count</p>
            <p className="font-mono text-2xl font-semibold text-slate-900" data-testid="summary-total-count-value">{analysis.summary?.total_count ?? 0}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="summary-top-issue-card">
            <p className="text-xs uppercase tracking-wide text-slate-500">Top Issue</p>
            <p className="text-sm font-semibold text-slate-900" data-testid="summary-top-issue-value">{analysis.summary?.top_issue || "N/A"}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="summary-top-area-card">
            <p className="text-xs uppercase tracking-wide text-slate-500">Most Impacted Area</p>
            <p className="text-sm font-semibold text-slate-900" data-testid="summary-top-area-value">{analysis.summary?.top_area || "N/A"}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="summary-awareness-change-card">
            <p className="text-xs uppercase tracking-wide text-slate-500">Awareness Change %</p>
            <p className="font-mono text-2xl font-semibold text-slate-900" data-testid="summary-awareness-change-value">{awarenessDisplay}</p>
          </div>
        </CardContent>
      </Card>

      <Card ref={tableRef} className="border border-slate-200 shadow-sm" data-testid="analysis-structured-table-section">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Structured Table</CardTitle>
          <CardDescription data-testid="analysis-table-context-text">
            {focusMode === "single-issue-multi-area" && "Table is grouped by area for the selected issue."}
            {focusMode === "single-area-multi-issue" && "Table is grouped by issue for the selected area."}
            {focusMode === "mixed" && "Table is grouped by area, issue, and phase."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {hasPhaseSplitTables && phaseTables.before?.length > 0 && renderStructuredTable(phaseTables.before, "Before Awareness Table", "before-awareness-table")}
          {hasPhaseSplitTables && phaseTables.after?.length > 0 && renderStructuredTable(phaseTables.after, "After Awareness Table", "after-awareness-table")}
          {!hasPhaseSplitTables && renderStructuredTable(tableRows, "Combined Table", "combined-awareness-table")}
          {hasPhaseSplitTables && phaseTables.unphased?.length > 0 && renderStructuredTable(phaseTables.unphased, "Unphased Table", "unphased-awareness-table")}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card ref={pieRef} className="border border-slate-200 shadow-sm" data-testid="issue-distribution-chart-card">
          <CardHeader>
            <CardTitle className="font-heading text-xl">{pieTitle}</CardTitle>
            <CardDescription>Labels are shown below to prevent overlap.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartCanvas testId="issue-distribution-chart-container" className="h-[550px]" style={{ overflow: "visible" }}>
              {({ width, height }) => (
                <PieChart width={width} height={height}>
                  <Pie
  data={pieData}
  dataKey="value"
  nameKey="name"
  cx="50%"
  cy="45%"
  outerRadius={Math.min(120, Math.floor(width * 0.28))}
  label={false}
  labelLine={false}
>

                    {pieData.map((item, index) => (
                      <Cell key={item.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              )}
            </ChartCanvas>
            <div className="mt-14 pb-8 grid gap-2 sm:grid-cols-2" data-testid="pie-chart-legend-grid">
              {pieData.map((item, index) => (
                <div
                  key={`${item.name}-${index}`}
                  className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs"
                  data-testid={`pie-chart-legend-item-${index}`}
                >
                  <span className="truncate" title={item.name}>{item.name}</span>
                  <span className="font-mono text-slate-900">{item.value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card ref={barRef} className="border border-slate-200 shadow-sm" data-testid="area-comparison-chart-card">
          <CardHeader>
            <CardTitle className="font-heading text-xl">{barTitle}</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartCanvas testId="area-comparison-chart-container" className="h-72">
              {({ width, height }) => (
                <BarChart width={width} height={height} data={barData} margin={{ top: 16, right: 10, left: 6, bottom: 36 }}>
                  <XAxis
                    dataKey="label"
                    angle={-18}
                    textAnchor="end"
                    interval={0}
                    height={66}
                    tickFormatter={toShortLabel}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  {lineMode === "awareness" ? (
                    <>
                      <Bar dataKey="before" name="Before Awareness" fill="#C2410C" radius={[8, 8, 0, 0]} />
                      <Bar dataKey="after" name="After Awareness" fill="#10B981" radius={[8, 8, 0, 0]} />
                    </>
                  ) : (
                    <Bar dataKey="count" fill="#0F172A" radius={[8, 8, 0, 0]} />
                  )}
                </BarChart>
              )}
            </ChartCanvas>
          </CardContent>
        </Card>
      </div>

      <Card ref={lineRef} className="border border-slate-200 shadow-sm" data-testid="line-comparison-chart-card">
        <CardHeader>
          <CardTitle className="font-heading text-xl">{lineTitle}</CardTitle>
        </CardHeader>
        <CardContent>
          <ChartCanvas testId="line-comparison-chart-container" className="h-[500px]">
            {({ width, height }) => (
              <LineChart width={width} height={height - 40} data={lineData} margin={{ top: 16, right: 10, left: 6, bottom: 36 }}>
                <XAxis
  dataKey="area"
  angle={-18}
  textAnchor="end"
  interval={0}
  height={66}
  tickFormatter={toShortLabel}
  tick={{ fontSize: 11 }}
/>
                <YAxis />
                <Tooltip />
                <Legend />
                {lineMode === "awareness" ? (
  <>
    <Line
      type="monotone"
      dataKey="before"
      stroke="#C2410C"
      strokeWidth={3}
      dot={{ r: 4 }}
    />
    <Line
      type="monotone"
      dataKey="after"
      stroke="#10B981"
      strokeWidth={3}
      dot={{ r: 4 }}
    />
  </>
) : (
  <Line
    type="monotone"
    dataKey="value"
    stroke="#0F172A"
    strokeWidth={3}
    dot={{ r: 4 }}
  />
)}
              </LineChart>
            )}
          </ChartCanvas>
        </CardContent>
      </Card>

      <Card ref={insightRef} className="border-l-4 border-l-emerald-500 border-r border-t border-b border-slate-200 bg-emerald-50 shadow-sm" data-testid="analysis-insight-card">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Automatic Insight</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-800 sm:text-base" data-testid="analysis-insight-text">{analysis.insight}</p>
        </CardContent>
      </Card>

      <Card className="border border-slate-200 shadow-sm" data-testid="download-section-card">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Download Options</CardTitle>
          <CardDescription>Download a combined report or individual sections as PDF.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button data-testid="download-combined-report-button" onClick={downloadCombined} className="bg-slate-900 text-white hover:bg-slate-800">Download Combined Report</Button>
          <Button data-testid="download-table-pdf-button" variant="outline" onClick={() => downloadSectionPdf(tableRef.current, "table-report.pdf")}>Table PDF</Button>
          <Button data-testid="download-pie-pdf-button" variant="outline" onClick={() => downloadSectionPdf(pieRef.current, "pie-chart-report.pdf")}>Pie Chart PDF</Button>
          <Button data-testid="download-bar-pdf-button" variant="outline" onClick={() => downloadSectionPdf(barRef.current, "bar-chart-report.pdf")}>Bar Chart PDF</Button>
          <Button data-testid="download-line-pdf-button" variant="outline" onClick={() => downloadSectionPdf(lineRef.current, "line-chart-report.pdf")}>Line Chart PDF</Button>
        </CardContent>
      </Card>
    </div>
  );
};

const ManualEntryPage = () => {
  const { userToken } = useAuth();
  const [rowForm, setRowForm] = useState({ area: "", issue: "", phase: "Before Awareness", count: "" });
  const [rows, setRows] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);

  const addRow = () => {
    if (!rowForm.area || !rowForm.issue || !rowForm.count) {
      toast.error("Please fill Area, Issue, and Count");
      return;
    }
    setRows((prev) => [
      ...prev,
      {
        area: rowForm.area,
        issue: rowForm.issue,
        phase: rowForm.phase,
        count: Number(rowForm.count),
      },
    ]);
    setRowForm((prev) => ({ ...prev, count: "" }));
  };

  const analyze = async () => {
    if (rows.length === 0) {
      toast.error("Add at least one row before analysis");
      return;
    }
    setLoading(true);
    try {
      const response = await api.post(
        "/analysis/manual",
        { rows, title: "Manual Entry Analysis" },
        authHeader(userToken),
      );
      setAnalysis(response.data);
      toast.success("Manual analysis completed");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="manual-entry-page">
      <h1 className="font-heading text-4xl font-extrabold tracking-tight text-slate-900" data-testid="manual-entry-title">Manual Data Entry</h1>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="border border-slate-200 shadow-sm lg:sticky lg:top-24 lg:h-fit" data-testid="manual-entry-form-card">
          <CardHeader>
            <CardTitle className="font-heading text-xl">Add Data Row</CardTitle>
            <CardDescription>Enter Area, Issue Type, Phase, and Count.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              data-testid="manual-area-input"
              placeholder="Area / Block"
              value={rowForm.area}
              onChange={(event) => setRowForm((prev) => ({ ...prev, area: event.target.value }))}
            />
            <Input
              list="issue-options"
              data-testid="manual-issue-input"
              placeholder="Issue Type"
              value={rowForm.issue}
              onChange={(event) => setRowForm((prev) => ({ ...prev, issue: event.target.value }))}
            />
            <datalist id="issue-options">
              {ISSUE_OPTIONS.map((issue) => (
                <option key={issue} value={issue} />
              ))}
            </datalist>
            <Select value={rowForm.phase} onValueChange={(value) => setRowForm((prev) => ({ ...prev, phase: value }))}>
              <SelectTrigger data-testid="manual-phase-select-trigger">
                <SelectValue placeholder="Select phase" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem data-testid="manual-phase-option-before" value="Before Awareness">Before Awareness</SelectItem>
                <SelectItem data-testid="manual-phase-option-after" value="After Awareness">After Awareness</SelectItem>
              </SelectContent>
            </Select>
            <Input
              data-testid="manual-count-input"
              type="number"
              min={0}
              placeholder="Count"
              value={rowForm.count}
              onChange={(event) => setRowForm((prev) => ({ ...prev, count: event.target.value }))}
            />
            <Button data-testid="manual-add-row-button" type="button" variant="outline" className="w-full" onClick={addRow}>Add Row</Button>
            <Button data-testid="manual-analyze-button" type="button" className="w-full bg-slate-900 text-white hover:bg-slate-800" onClick={analyze} disabled={loading}>
              {loading ? "Analyzing..." : "Analyze"}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card className="border border-slate-200 shadow-sm" data-testid="manual-entered-rows-card">
            <CardHeader>
              <CardTitle className="font-heading text-xl">Entered Rows</CardTitle>
            </CardHeader>
            <CardContent>
              <Table data-testid="manual-entered-rows-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Area</TableHead>
                    <TableHead>Issue</TableHead>
                    <TableHead>Phase</TableHead>
                    <TableHead>Count</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center text-slate-500" data-testid="manual-empty-rows-message">No rows added yet.</TableCell>
                    </TableRow>
                  ) : (
                    rows.map((row, index) => (
                      <TableRow key={`${row.area}-${index}`} data-testid={`manual-entered-row-${index}`}>
                        <TableCell>{row.area}</TableCell>
                        <TableCell>{row.issue}</TableCell>
                        <TableCell>{row.phase}</TableCell>
                        <TableCell>{row.count}</TableCell>
                        <TableCell>
                          <Button
                            data-testid={`manual-remove-row-button-${index}`}
                            variant="outline"
                            size="sm"
                            onClick={() => setRows((prev) => prev.filter((_, itemIndex) => itemIndex !== index))}
                          >
                            Remove
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <ResultsPanel analysis={analysis} sectionLabel="Manual Entry" />
        </div>
      </div>
    </div>
  );
};

const TextInputPage = () => {
  const { userToken } = useAuth();
  const [text, setText] = useState("Before Awareness:\nPatna : environment 15\nSiwan : environment 20\n\nAfter Awareness:\nPatna : environment 11\nSiwan : environment 14");
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);

  const analyzeText = async () => {
    if (!text.trim()) {
      toast.error("Please enter text input");
      return;
    }
    setLoading(true);
    try {
      const response = await api.post(
        "/analysis/text",
        { text, title: "Text Input Analysis" },
        authHeader(userToken),
      );
      setAnalysis(response.data);
      toast.success("Text analysis completed");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to analyze text");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="text-input-page">
      <h1 className="font-heading text-4xl font-extrabold tracking-tight text-slate-900" data-testid="text-input-title">Natural Language Text Input</h1>
      <Card className="border border-slate-200 shadow-sm" data-testid="text-input-form-card">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Paste Issue Text</CardTitle>
          <CardDescription>Flexible parser supports Before/After Awareness text, comma-separated entries, and multiline formats.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            data-testid="text-input-textarea"
            className="min-h-[300px] font-mono text-sm"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <Button data-testid="text-input-analyze-button" className="bg-slate-900 text-white hover:bg-slate-800" onClick={analyzeText} disabled={loading}>
            {loading ? "Parsing & analyzing..." : "Parse & Analyze"}
          </Button>
        </CardContent>
      </Card>
      <ResultsPanel analysis={analysis} sectionLabel="Text Input" />
    </div>
  );
};

const FileUploadPage = () => {
  const { userToken } = useAuth();
  const [file, setFile] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);

  const uploadAndAnalyze = async () => {
    if (!file) {
      toast.error("Please select a CSV or XLSX file");
      return;
    }
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", "File Upload Analysis");
      const response = await api.post("/analysis/file", formData, {
        ...authHeader(userToken),
        headers: {
          ...authHeader(userToken).headers,
          "Content-Type": "multipart/form-data",
        },
      });
      setAnalysis(response.data);
      toast.success("File processed successfully");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "File analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="file-upload-page">
      <h1 className="font-heading text-4xl font-extrabold tracking-tight text-slate-900" data-testid="file-upload-title">File Upload Analysis</h1>
      <Card className="border border-slate-200 shadow-sm" data-testid="file-upload-form-card">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Upload Dataset</CardTitle>
          <CardDescription>Supported formats: CSV, XLSX</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-xl border-2 border-dashed border-slate-300 bg-white p-8 text-center" data-testid="file-upload-dropzone">
            <Input
              data-testid="file-upload-input"
              type="file"
              accept=".csv,.xlsx"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
            <p className="mt-3 text-sm text-slate-500" data-testid="file-upload-selected-file-name">{file ? file.name : "No file selected yet"}</p>
          </div>
          <Button data-testid="file-upload-analyze-button" className="bg-slate-900 text-white hover:bg-slate-800" onClick={uploadAndAnalyze} disabled={loading}>
            {loading ? "Processing..." : "Analyze Uploaded File"}
          </Button>
        </CardContent>
      </Card>

      {analysis?.file_metadata && (
        <Card className="border border-slate-200 shadow-sm" data-testid="file-upload-metadata-card">
          <CardContent className="grid gap-2 pt-6 text-sm text-slate-700">
            <p data-testid="file-upload-metadata-filename"><strong>File:</strong> {analysis.file_metadata.filename}</p>
            <p data-testid="file-upload-metadata-type"><strong>Type:</strong> {analysis.file_metadata.content_type || "Unknown"}</p>
            <p data-testid="file-upload-metadata-size"><strong>Size (bytes):</strong> {analysis.file_metadata.size_bytes}</p>
          </CardContent>
        </Card>
      )}

      <ResultsPanel analysis={analysis} sectionLabel="File Upload" />
    </div>
  );
};

const CommunityFormPage = () => {
  const { userToken } = useAuth();
  const [form, setForm] = useState({ area: "", issue_type: "", description: "" });
  const [loading, setLoading] = useState(false);

  const submitForm = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      await api.post("/community/submit", form, authHeader(userToken));
      toast.success("Community observation submitted");
      setForm({ area: "", issue_type: "", description: "" });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Submission failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="community-form-page">
      <h1 className="font-heading text-4xl font-extrabold tracking-tight text-slate-900" data-testid="community-form-title">Community Data Submission Form</h1>
      <Card className="border border-slate-200 shadow-sm" data-testid="community-form-card">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Submit Observation</CardTitle>
          <CardDescription data-testid="community-form-message">
            This platform collects community data for awareness research purposes.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={submitForm} data-testid="community-form">
            <Input
              data-testid="community-form-area-input"
              placeholder="Area"
              value={form.area}
              onChange={(event) => setForm((prev) => ({ ...prev, area: event.target.value }))}
              required
            />
            <Input
              data-testid="community-form-issue-type-input"
              placeholder="Issue Type"
              value={form.issue_type}
              onChange={(event) => setForm((prev) => ({ ...prev, issue_type: event.target.value }))}
              required
            />
            <Textarea
              data-testid="community-form-description-input"
              placeholder="Description"
              value={form.description}
              onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
              required
            />
            <Button data-testid="community-form-submit-button" type="submit" className="bg-slate-900 text-white hover:bg-slate-800" disabled={loading}>
              {loading ? "Submitting..." : "Submit Observation"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

const HistoryPage = () => {
  const { userToken } = useAuth();
  const [records, setRecords] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get("/analysis/history", authHeader(userToken));
      setRecords(response.data);
      setSelected(response.data[0] || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, [userToken]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const deleteRecord = async (recordId) => {
    try {
      await api.delete(`/analysis/history/${recordId}`, authHeader(userToken));
      toast.success("History record deleted");
      await fetchHistory();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Delete failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="history-page">
      <h1 className="font-heading text-4xl font-extrabold tracking-tight text-slate-900" data-testid="history-title">My Analysis History</h1>
      <Card className="border border-slate-200 shadow-sm" data-testid="history-list-card">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Private Records</CardTitle>
          <CardDescription>Only your analysis records are shown here.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-slate-500" data-testid="history-loading-text">Loading history...</p>
          ) : records.length === 0 ? (
            <p className="text-sm text-slate-500" data-testid="history-empty-text">No history records yet.</p>
          ) : (
            <div className="space-y-3">
              {records.map((record, index) => (
                <div
                  key={record.id}
                  className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4 ${selected?.id === record.id ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"}`}
                  data-testid={`history-record-item-${index}`}
                >
                  <div className="space-y-1">
                    <p className="font-semibold text-slate-900" data-testid={`history-record-title-${index}`}>{record.title}</p>
                    <p className="text-xs text-slate-500" data-testid={`history-record-meta-${index}`}>
                      {record.source_type.toUpperCase()} • {formatDate(record.created_at)}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button data-testid={`history-view-button-${index}`} variant="outline" onClick={() => setSelected(record)}>View</Button>
                    <Button data-testid={`history-delete-button-${index}`} variant="outline" onClick={() => deleteRecord(record.id)}>Delete</Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      <ResultsPanel analysis={selected} sectionLabel="History" />
    </div>
  );
};

const AdminLoginPage = () => {
  const { adminLogin } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("IITPATNACAPSTONE");
  const [password, setPassword] = useState("computerscience");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      await adminLogin({ username, password });
      toast.success("Admin login successful");
      setTimeout(() => {
  navigate("/admin/dashboard");
}, 100);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Admin login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg" data-testid="admin-login-page">
      <Card className="border border-slate-200 shadow-sm">

  <CardHeader>
    <CardTitle className="font-heading text-2xl">
      Admin Login
    </CardTitle>
  </CardHeader>

  <CardContent>
    <form className="space-y-4" onSubmit={handleSubmit} data-testid="admin-login-form">
            <Input
              data-testid="admin-login-username-input"
              placeholder="Username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
            <Input
              data-testid="admin-login-password-input"
              type="password"
              placeholder="Password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <Button data-testid="admin-login-submit-button" type="submit" className="w-full bg-slate-900 text-white hover:bg-slate-800" disabled={loading}>
              {loading ? "Signing in..." : "Admin Login"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

const AdminDashboardPage = () => {
  const { adminToken, adminUsername } = useAuth();
  const [submissions, setSubmissions] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [credentialForm, setCredentialForm] = useState({ old_password: "", new_password: "", new_username: "" });

  const fetchAdminData = useCallback(async () => {
    setLoading(true);
    try {
      const [submissionsResponse, datasetsResponse] = await Promise.all([
        api.get("/admin/submissions", authHeader(adminToken)),
        api.get("/admin/datasets", authHeader(adminToken)),
      ]);
      setSubmissions(submissionsResponse.data);
      setDatasets(datasetsResponse.data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Unable to load admin data");
    } finally {
      setLoading(false);
    }
  }, [adminToken]);

  useEffect(() => {
    fetchAdminData();
  }, [fetchAdminData]);

  const deleteSubmission = async (submissionId) => {
    try {
      await api.delete(`/admin/submissions/${submissionId}`, authHeader(adminToken));
      toast.success("Submission deleted");
      fetchAdminData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Delete failed");
    }
  };

  const deleteDataset = async (analysisId) => {
    try {
      await api.delete(`/admin/analyses/${analysisId}`, authHeader(adminToken));
      toast.success("Dataset deleted");
      fetchAdminData();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Delete failed");
    }
  };

  const exportCsv = async (path, filename) => {
    try {
      const response = await api.get(path, { ...authHeader(adminToken), responseType: "blob" });
      downloadBlob(response.data, filename);
    } catch {
      toast.error("Export failed");
    }
  };

  const changeCredentials = async (event) => {
    event.preventDefault();
    try {
      await api.post("/admin/change-password", credentialForm, authHeader(adminToken));
      toast.success("Admin credentials updated");
      setCredentialForm({ old_password: "", new_password: "", new_username: "" });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Update failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="admin-dashboard-page">
      <h1 className="font-heading text-4xl font-extrabold tracking-tight text-slate-900" data-testid="admin-dashboard-title">Admin Dashboard</h1>
      <p className="text-sm text-slate-600" data-testid="admin-dashboard-username-text">Logged in as: {adminUsername}</p>

      <Card className="border border-slate-200 shadow-sm" data-testid="admin-credential-update-card">
        <CardHeader>
          <CardTitle className="font-heading text-xl">Change Admin Credentials</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-4" onSubmit={changeCredentials} data-testid="admin-credential-update-form">
            <Input
              data-testid="admin-old-password-input"
              type="password"
              placeholder="Old Password"
              value={credentialForm.old_password}
              onChange={(event) => setCredentialForm((prev) => ({ ...prev, old_password: event.target.value }))}
              required
            />
            <Input
              data-testid="admin-new-password-input"
              type="password"
              placeholder="New Password"
              value={credentialForm.new_password}
              onChange={(event) => setCredentialForm((prev) => ({ ...prev, new_password: event.target.value }))}
              required
            />
            <Input
              data-testid="admin-new-username-input"
              placeholder="New Username (optional)"
              value={credentialForm.new_username}
              onChange={(event) => setCredentialForm((prev) => ({ ...prev, new_username: event.target.value }))}
            />
            <Button data-testid="admin-update-credentials-button" type="submit" className="bg-slate-900 text-white hover:bg-slate-800">Update</Button>
          </form>
        </CardContent>
      </Card>

      <Card className="border border-slate-200 shadow-sm" data-testid="admin-submissions-card">
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="font-heading text-xl">Community Submissions</CardTitle>
            <CardDescription>Global submissions visible only to admin.</CardDescription>
          </div>
          <Button data-testid="admin-export-submissions-button" variant="outline" onClick={() => exportCsv("/admin/export/submissions", "community_submissions.csv")}>Export Submissions</Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-slate-500" data-testid="admin-submissions-loading">Loading...</p>
          ) : (
            <Table data-testid="admin-submissions-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Area</TableHead>
                  <TableHead>Issue</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {submissions.map((item, index) => (
                  <TableRow key={item.id} data-testid={`admin-submission-row-${index}`}>
                    <TableCell>{item.user_email}</TableCell>
                    <TableCell>{item.area}</TableCell>
                    <TableCell>{item.issue_type}</TableCell>
                    <TableCell className="max-w-xs truncate">{item.description}</TableCell>
                    <TableCell>
                      <Button data-testid={`admin-delete-submission-button-${index}`} variant="outline" onClick={() => deleteSubmission(item.id)}>Delete</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card className="border border-slate-200 shadow-sm" data-testid="admin-datasets-card">
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="font-heading text-xl">Uploaded Datasets</CardTitle>
            <CardDescription>File analyses across all users.</CardDescription>
          </div>
          <Button data-testid="admin-export-datasets-button" variant="outline" onClick={() => exportCsv("/admin/export/datasets", "uploaded_datasets.csv")}>Export Datasets</Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-slate-500" data-testid="admin-datasets-loading">Loading...</p>
          ) : (
            <Table data-testid="admin-datasets-table">
              <TableHeader>
                <TableRow>
                  <TableHead>User ID</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>File</TableHead>
                  <TableHead>Rows</TableHead>
                  <TableHead>Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {datasets.map((item, index) => (
                  <TableRow key={item.id} data-testid={`admin-dataset-row-${index}`}>
                    <TableCell className="font-mono text-xs">{item.user_id}</TableCell>
                    <TableCell>{item.title}</TableCell>
                    <TableCell>{item.file_metadata?.filename || "N/A"}</TableCell>
                    <TableCell>{item.rows?.length || 0}</TableCell>
                    <TableCell>
                      <Button data-testid={`admin-delete-dataset-button-${index}`} variant="outline" onClick={() => deleteDataset(item.id)}>Delete</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppLayout>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/manual-entry" element={<ProtectedRoute><ManualEntryPage /></ProtectedRoute>} />
            <Route path="/text-input" element={<ProtectedRoute><TextInputPage /></ProtectedRoute>} />
            <Route path="/file-upload" element={<ProtectedRoute><FileUploadPage /></ProtectedRoute>} />
            <Route path="/community-form" element={<ProtectedRoute><CommunityFormPage /></ProtectedRoute>} />
            <Route path="/history" element={<ProtectedRoute><HistoryPage /></ProtectedRoute>} />
            <Route path="/admin/login" element={<AdminLoginPage />} />
            <Route path="/admin/dashboard" element={<AdminRoute><AdminDashboardPage /></AdminRoute>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppLayout>
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
