import { lazy, Suspense, useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Box,
  ChevronLeft,
  CircleHelp,
  ExternalLink,
  FolderClosed,
  Grid2X2,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldCheck,
  Sun,
  Upload,
  Workflow,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  applyTheme,
  currentView,
  initialTheme,
  readPreference,
  writePreference,
  type View,
} from "@/lib/preferences";
import { cn } from "@/lib/utils";

const Dashboard = lazy(() => import("@/components/views/Dashboard"));
const sections = [
  {
    id: "overview",
    label: "总览",
    icon: Grid2X2,
    description: "从这里，掌握每一个创作环节。",
  },
  {
    id: "tasks",
    label: "任务与流程",
    icon: Workflow,
    description: "任务箱、五个生产步骤与项目状态。",
  },
  {
    id: "uploads",
    label: "上传",
    icon: Upload,
    description: "成片上传、云端核验与安全清理状态。",
  },
  {
    id: "files",
    label: "文件管理",
    icon: FolderClosed,
    description: "草稿、音频、生产文件与待删区。",
  },
  {
    id: "commands",
    label: "安全继续与命令",
    icon: ShieldCheck,
    description: "HTTP 回执与业务进度分别呈现。",
  },
  {
    id: "health",
    label: "健康与事件",
    icon: Activity,
    description: "系统服务、确定性安全检查与最近事件。",
  },
] as const;

function Brand() {
  return (
    <a className="brand" href="#overview" aria-label="自动剪辑 · 总览">
      <span className="brand-symbol">
        <Grid2X2 size={21} strokeWidth={1.8} />
      </span>
      <span className="brand-copy">
        <strong>自动剪辑</strong>
        <span>WORKSPACE / V2</span>
      </span>
    </a>
  );
}

function Navigation({
  view,
  collapsed,
  onNavigate,
}: {
  view: View;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav aria-label="控制台分区" className="navigation">
      <p className="nav-caption">工作空间</p>
      {sections.map(({ id, label, icon: Icon }) => {
        const link = (
          <a
            href={`#${id}`}
            className={cn("nav-item", view === id && "is-active")}
            aria-current={view === id ? "page" : undefined}
            aria-label={collapsed ? label : undefined}
            onClick={onNavigate}
          >
            <Icon size={18} strokeWidth={1.7} />
            <span className="nav-label">{label}</span>
            <span className="nav-active-mark" aria-hidden="true" />
          </a>
        );
        return collapsed ? (
          <Tooltip key={id}>
            <TooltipTrigger asChild>{link}</TooltipTrigger>
            <TooltipContent side="right">{label}</TooltipContent>
          </Tooltip>
        ) : (
          <div key={id}>{link}</div>
        );
      })}
    </nav>
  );
}

function SidebarFooter() {
  return (
    <div className="sidebar-footer">
      <Separator />
      <div className="sidebar-note">
        <Box size={16} />
        <span>独立预览空间</span>
        <Badge variant="outline">V2-2B</Badge>
      </div>
      <p>专注创作，让流程井然有序。</p>
    </div>
  );
}

export default function App() {
  const [theme, setTheme] = useState(initialTheme);
  const [view, setView] = useState(currentView);
  const [collapsed, setCollapsed] = useState(
    () => readPreference("sidebar") === "collapsed",
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const current = sections.find((section) => section.id === view)!;
  const CurrentIcon = current.icon;

  useEffect(() => {
    const onHashChange = () => setView(currentView());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    writePreference("theme", next);
    setTheme(next);
  }

  function toggleSidebar() {
    writePreference("sidebar", !collapsed ? "collapsed" : "expanded");
    setCollapsed(!collapsed);
  }

  return (
    <TooltipProvider delayDuration={250}>
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        跳到内容
      </a>
      <div className={cn("app-shell", collapsed && "sidebar-collapsed")}>
        <aside className="desktop-sidebar" aria-label="侧栏">
          <Brand />
          <Navigation view={view} collapsed={collapsed} />
          <div className="sidebar-bottom">
            <SidebarFooter />
            <Button
              variant="ghost"
              className="collapse-button"
              onClick={toggleSidebar}
              aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
              aria-expanded={!collapsed}
            >
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
              <span className="nav-label">收起侧栏</span>
            </Button>
          </div>
        </aside>

        <div className="workspace">
          <header className="topbar">
            <div className="topbar-leading">
              <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                <SheetTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="mobile-menu"
                    aria-label="打开导航"
                  >
                    <Menu />
                  </Button>
                </SheetTrigger>
                <SheetContent
                  side="left"
                  className="mobile-sidebar"
                  aria-describedby="mobile-navigation-description"
                >
                  <SheetTitle className="sr-only">控制台导航</SheetTitle>
                  <SheetDescription
                    id="mobile-navigation-description"
                    className="sr-only"
                  >
                    选择一个控制台分区。当前开放上传和任务操作，其他操作请用旧页面。
                  </SheetDescription>
                  <Brand />
                  <Navigation
                    view={view}
                    collapsed={false}
                    onNavigate={() => setMobileOpen(false)}
                  />
                  <SidebarFooter />
                </SheetContent>
              </Sheet>
              <span className="breadcrumb-root">控制台</span>
              <ChevronLeft className="breadcrumb-divider" size={13} />
              <span className="breadcrumb-current">{current.label}</span>
            </div>
            <div className="topbar-actions">
              <Badge variant="outline" className="preview-badge">
                V2 功能预览
              </Badge>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={toggleTheme}
                    aria-label={
                      theme === "dark" ? "切换到浅色主题" : "切换到深色主题"
                    }
                  >
                    {theme === "dark" ? <Sun /> : <Moon />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>切换外观</TooltipContent>
              </Tooltip>
              <Separator orientation="vertical" className="topbar-separator" />
              <Button variant="ghost" size="sm" asChild className="legacy-link">
                <a href="/" target="_blank" rel="noreferrer">
                  旧版控制台
                  <ArrowUpRight size={14} />
                </a>
              </Button>
            </div>
          </header>

          <main id="main-content" className="main-content" tabIndex={-1}>
            <div className="page-heading">
              <div>
                <div className="eyebrow">
                  <span />
                  WORKSPACE OVERVIEW
                </div>
                <h1>{current.label}</h1>
                <p>{current.description}</p>
              </div>
              <span className="section-icon" aria-hidden="true">
                <CurrentIcon size={24} strokeWidth={1.3} />
              </span>
            </div>
            <Suspense
              fallback={
                <Skeleton
                  className="empty-skeleton"
                  aria-label="正在载入只读视图"
                />
              }
            >
              <Dashboard view={view} />
            </Suspense>

            <Card className="continuity-card">
              <div className="continuity-icon">
                <CircleHelp size={19} strokeWidth={1.5} />
              </div>
              <div>
                <h2>原来的工作空间，随时可用</h2>
                <p>
                  当前预览不会代替旧页面。查看任务与执行操作，请继续使用旧版控制台。
                </p>
              </div>
              <Button variant="outline" size="sm" asChild>
                <a href="/" target="_blank" rel="noreferrer">
                  打开旧页面
                  <ExternalLink size={13} />
                </a>
              </Button>
            </Card>
            <footer className="page-footer">
              <span>
                自动剪辑 <span className="footer-dot">·</span> 控制台 V2
              </span>
              <span>V2 预览 / 上传与任务操作预览</span>
            </footer>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
