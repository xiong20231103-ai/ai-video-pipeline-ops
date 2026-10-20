import { Panel } from "@/components/views/shared";
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { BlurText, CountUp, FadeContent } from "@/components/react-bits/Motion";
import { ToastHost } from "@/components/views/Feedback";
import { useFeedback } from "@/data/use-feedback";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it("reduced motion disables title animation and numeric frames", () => {
  vi.spyOn(window, "matchMedia").mockReturnValue({
    matches: true,
  } as MediaQueryList);
  const frame = vi.spyOn(window, "requestAnimationFrame"),
    animate = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    value: animate,
  });
  render(
    <>
      <BlurText text="减少动效隔离" />
      <CountUp value="18.5%" />
    </>,
  );
  expect(animate).not.toHaveBeenCalled();
  expect(frame).not.toHaveBeenCalled();
  expect(screen.getByText("18.5%")).toBeInTheDocument();
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).animate;
});
it("unchanged numeric refresh schedules no new animation; changed value reaches exact target", () => {
  vi.spyOn(window, "matchMedia").mockReturnValue({
    matches: false,
  } as MediaQueryList);
  let callback: FrameRequestCallback = () => {};
  const raf = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((fn) => {
        callback = fn;
        return 7;
      }),
    cancel = vi
      .spyOn(window, "cancelAnimationFrame")
      .mockImplementation(() => {});
  const now = vi.spyOn(performance, "now").mockReturnValue(0);
  const view = render(<CountUp value="15.2%" />);
  expect(raf).toHaveBeenCalledTimes(1);
  act(() => callback(500));
  expect(screen.getByText("15.2%")).toBeInTheDocument();
  view.rerender(<CountUp value="15.2%" />);
  expect(raf).toHaveBeenCalledTimes(1);
  now.mockReturnValue(500);
  view.rerender(<CountUp value="19.8%" />);
  expect(raf).toHaveBeenCalledTimes(2);
  act(() => callback(1000));
  expect(screen.getByText("19.8%")).toBeInTheDocument();
  view.unmount();
  expect(cancel).toHaveBeenCalled();
});
it("finished title animation only plays once across repeated renders and remount", () => {
  vi.spyOn(window, "matchMedia").mockReturnValue({
    matches: false,
  } as MediaQueryList);
  const animation = { cancel: vi.fn(), onfinish: null as null | (() => void) },
    animate = vi.fn().mockReturnValue(animation);
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    value: animate,
  });
  const view = render(<BlurText text="标题仅首次隔离" />);
  expect(animate).toHaveBeenCalledTimes(1);
  act(() => animation.onfinish?.());
  view.rerender(<BlurText text="标题仅首次隔离" />);
  expect(animate).toHaveBeenCalledTimes(1);
  view.unmount();
  render(<BlurText text="标题仅首次隔离" />);
  expect(animate).toHaveBeenCalledTimes(1);
  delete (HTMLElement.prototype as unknown as Record<string, unknown>).animate;
});
it("card observer disconnects on unmount and repeated data does not recreate it", () => {
  vi.spyOn(window, "matchMedia").mockReturnValue({
    matches: false,
  } as MediaQueryList);
  const disconnect = vi.fn(),
    observe = vi.fn(),
    Observer = vi.fn().mockImplementation(function () {
      return { observe, disconnect };
    });
  vi.stubGlobal("IntersectionObserver", Observer);
  const view = render(
    <FadeContent id="隔离观察器">
      <p>首次卡片</p>
    </FadeContent>,
  );
  view.rerender(
    <FadeContent id="隔离观察器">
      <p>刷新内容</p>
    </FadeContent>,
  );
  expect(Observer).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(disconnect).toHaveBeenCalledTimes(1);
  vi.unstubAllGlobals();
});
function FeedbackExample({ message }: { message: string }) {
  useFeedback(message);
  return <ToastHost />;
}
it("toast only announces changed action feedback, expires and cleans listener", () => {
  vi.useFakeTimers();
  const view = render(<FeedbackExample message="" />);
  view.rerender(<FeedbackExample message="模拟请求已排队" />);
  expect(screen.getByRole("status")).toHaveTextContent("模拟请求已排队");
  act(() => vi.advanceTimersByTime(5001));
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  view.rerender(<FeedbackExample message="模拟请求已排队" />);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  view.rerender(<FeedbackExample message="模拟校验失败" />);
  expect(screen.getByRole("status")).toHaveTextContent("模拟校验失败");
  view.unmount();
  act(() =>
    window.dispatchEvent(
      new CustomEvent("ops-v2-feedback", { detail: { message: "unmounted" } }),
    ),
  );
  expect(vi.getTimerCount()).toBe(0);
});

it("dynamic offline title does not recreate the card observer when its stable id is unchanged", () => {
  vi.spyOn(window, "matchMedia").mockReturnValue({
    matches: false,
  } as MediaQueryList);
  const disconnect = vi.fn(),
    observe = vi.fn(),
    Observer = vi.fn().mockImplementation(function () {
      return { observe, disconnect };
    });
  vi.stubGlobal("IntersectionObserver", Observer);
  const view = render(
    <Panel motionId="isolated-cloud-source" title="离线 10 秒">
      内容
    </Panel>,
  );
  for (const age of [20, 30, 40, 50])
    view.rerender(
      <Panel motionId="isolated-cloud-source" title={"离线 " + age + " 秒"}>
        内容
      </Panel>,
    );
  expect(Observer).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(disconnect).toHaveBeenCalledTimes(1);
  vi.unstubAllGlobals();
});
