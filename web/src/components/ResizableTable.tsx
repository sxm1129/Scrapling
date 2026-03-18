"use client";
import React, { useEffect, useRef } from "react";

export default function ResizableTable({ 
  children, 
  id, 
  stickyFirstCol = true 
}: { 
  children: React.ReactNode, 
  id: string,
  stickyFirstCol?: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const table = containerRef.current?.querySelector("table");
    if (!table) return;

    // Must be fixed layout for widths to be respected properly
    table.style.tableLayout = "fixed";
    table.style.width = "max-content";
    table.style.minWidth = "100%";

    const ths = Array.from(table.querySelectorAll("th"));
    if (ths.length === 0) return;

    // Load saved widths
    const saved = localStorage.getItem(`kashi_table_widths_${id}`);
    const widths: Record<number, number> = saved ? JSON.parse(saved) : {};

    ths.forEach((th, idx) => {
      // Apply saved width, except last column which can flexibly take remaining space
      // Actually table-layout fixed + width=max-content means it might not auto-fill.
      // So we set width on all or let last one be auto.
      if (widths[idx]) {
        th.style.width = `${widths[idx]}px`;
        th.style.minWidth = `${widths[idx]}px`;
      } else if (!th.style.width) {
        // default minimum width to ensure decent display
        th.style.width = "120px";
        th.style.minWidth = "120px";
      }

      // 1. Apply sticky if needed
      if (stickyFirstCol && idx === 0) {
        th.classList.add("sticky-col");
      }

      // Avoid double adding
      if (th.querySelector(".resize-handle")) return;

      // Ensure TH is relative
      th.style.position = th.style.position === "sticky" ? "sticky" : "relative";

      // 2. Add resize handle
      const handle = document.createElement("div");
      handle.className = "resize-handle";
      th.appendChild(handle);

      let startX = 0;
      let startWidth = 0;

      const onMouseMove = (e: MouseEvent) => {
        const diff = e.pageX - startX;
        let finalWidth = Math.max(60, startWidth + diff); // min width 60
        th.style.width = `${finalWidth}px`;
        th.style.minWidth = `${finalWidth}px`;
        widths[idx] = finalWidth;
      };

      const onMouseUp = () => {
        handle.classList.remove("active");
        document.body.style.cursor = "default";
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
        localStorage.setItem(`kashi_table_widths_${id}`, JSON.stringify(widths));
      };

      handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation(); // Avoid triggering sorts if any
        startX = e.pageX;
        startWidth = th.offsetWidth;
        handle.classList.add("active");
        document.body.style.cursor = "col-resize";
        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
      });
    });

    // Also apply sticky class to first td of each row
    if (stickyFirstCol) {
      const rows = Array.from(table.querySelectorAll("tbody tr"));
      rows.forEach(row => {
        const firstTd = row.querySelector("td");
        if (firstTd) firstTd.classList.add("sticky-col");
      });
    }

  }, [children, id, stickyFirstCol]);

  return (
    <div className="resizable-table-container" ref={containerRef} style={{ overflowX: "auto", position: "relative", width: "100%" }}>
      {children}
    </div>
  );
}
