import { legacyDestination } from "@/lib/entry";
import { BlurText } from "@/components/react-bits/Motion";
import { ToastHost } from "@/components/views/Feedback";
import { lazy, Suspense, useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  ChevronLeft,
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
import { Button } from "@/components/ui/button";
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
  },
  {
    id: "tasks",
    label: "任务与流程",
    icon: Workflow,
  },
  {
    id: "uploads",
    label: "上传",
    icon: Upload,
  },
  {
    id: "files",
    label: "文件管理",
    icon: FolderClosed,
  },
  {
    id: "commands",
    label: "安全继续与命令",
    icon: ShieldCheck,
  },
  {
    id: "health",
    label: "健康与事件",
    icon: Activity,
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
        <span>生产控制台</span>
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

export default function App() {
  const [theme, setTheme] = useState(initialTheme);
  const [view, setView] = useState(currentView);
  const [collapsed, setCollapsed] = useState(
    () => readPreference("sidebar") === "collapsed",
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const current = sections.find((section) => section.id === view)!;

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
      <ToastHost />
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
                    选择一个控制台分区。操作资格由当前模式与服务状态决定。
                  </SheetDescription>
                  <Brand />
                  <Navigation
                    view={view}
                    collapsed={false}
                    onNavigate={() => setMobileOpen(false)}
                  />
                </SheetContent>
              </Sheet>
              <span className="breadcrumb-root">控制台</span>
              <ChevronLeft className="breadcrumb-divider" size={13} />
              <span className="breadcrumb-current">{current.label}</span>
            </div>
            <div className="topbar-actions">
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
                <a href={legacyDestination} target="_blank" rel="noreferrer">
                  旧版控制台
                  <ArrowUpRight size={14} />
                </a>
              </Button>
            </div>
          </header>

          <main id="main-content" className="main-content" tabIndex={-1}>
            <div className="page-heading">
              <h1>
                <BlurText text={current.label} />
              </h1>
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

            <footer className="page-footer">
              <span>
                自动剪辑 <span className="footer-dot">·</span> 生产控制台
              </span>
              <span>业务进度以家里状态为准</span>
            </footer>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
