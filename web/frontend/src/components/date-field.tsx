"use client";

import { useEffect, useId, useRef, useState } from "react";
import {
  CalendarBlankIcon,
  CaretLeftIcon,
  CaretRightIcon,
  XIcon,
} from "@phosphor-icons/react";

/** A text field and HTML calendar. Values use YYYY-MM-DD, without timezone conversion.
 * onChange emits only valid in-range dates, or "" when an optional field is cleared.
 * Invalid drafts stay visible and set native form customValidity, preventing a
 * required upload form from submitting its previous valid value. No native date
 * picker, showPicker(), or third-party calendar dependency is used.
 */
export interface DateFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  min?: string;
  max?: string;
  required?: boolean;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export function isValidDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T12:00:00Z`);
  return (
    Number.isFinite(date.getTime()) &&
    date.toISOString().slice(0, 10) === value &&
    value.slice(0, 4) !== "0000"
  );
}

function todayDate(): string {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
}

function monthOf(value: string): string {
  return value.slice(0, 7);
}

function shiftMonth(month: string, amount: number): string {
  const date = new Date(`${month}-01T12:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() + amount);
  return date.toISOString().slice(0, 7);
}

export function DateField({
  label,
  value,
  onChange,
  min,
  max,
  required = false,
  disabled = false,
  id,
  className = "",
}: DateFieldProps) {
  const generatedId = useId();
  const inputId = id || `date-${generatedId}`;
  const panelId = `${inputId}-calendar`;
  const errorId = `${inputId}-error`;
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const focusDate = useRef<string | null>(null);
  const [draft, setDraft] = useState({ source: value, text: value });
  const [touched, setTouched] = useState(false);
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() =>
    monthOf(isValidDate(value) ? value : todayDate()),
  );
  const [position, setPosition] = useState({ top: 0, left: 0 });
  // A new controlled value immediately replaces any stale keyboard draft.
  const text = draft.source === value ? draft.text : value;
  const validation = !text
    ? required
      ? `請填寫${label}。`
      : ""
    : !isValidDate(text)
      ? "請輸入有效日期，格式為 YYYY-MM-DD。"
      : min && text < min
        ? `日期不可早於 ${min}。`
        : max && text > max
          ? `日期不可晚於 ${max}。`
          : "";

  useEffect(() => {
    input.current?.setCustomValidity(validation);
  }, [validation]);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnResize = () => setOpen(false);
    document.addEventListener("pointerdown", closeOutside);
    window.addEventListener("resize", closeOnResize);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      window.removeEventListener("resize", closeOnResize);
    };
  }, [open]);

  useEffect(() => {
    if (open && focusDate.current) {
      panel.current
        ?.querySelector<HTMLButtonElement>(
          `button[data-date="${focusDate.current}"]`,
        )
        ?.focus();
      focusDate.current = null;
    }
  }, [open, month]);

  const inRange = (date: string) =>
    isValidDate(date) && (!min || date >= min) && (!max || date <= max);
  const close = () => {
    setOpen(false);
    input.current?.focus();
  };
  const choose = (date: string) => {
    if (date && !inRange(date)) return;
    setDraft({ source: value, text: date });
    setTouched(true);
    input.current?.setCustomValidity(
      !date && required ? `請填寫${label}。` : "",
    );
    if (date || !required) onChange(date);
    close();
  };
  const toggle = () => {
    if (disabled) return;
    if (open) {
      close();
      return;
    }
    const rect = root.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(286, window.innerWidth - 32);
    const popupHeight = 390;
    setPosition({
      left: Math.max(16, Math.min(rect.left, window.innerWidth - width - 16)),
      top:
        rect.bottom + popupHeight + 8 <= window.innerHeight
          ? rect.bottom + 8
          : Math.max(16, rect.top - popupHeight - 8),
    });
    const candidate = isValidDate(text) ? text : todayDate();
    const initial =
      min && candidate < min ? min : max && candidate > max ? max : candidate;
    setMonth(monthOf(initial));
    focusDate.current = initial;
    setOpen(true);
  };
  const updateText = (next: string) => {
    setDraft({ source: value, text: next });
    setTouched(true);
    if ((!next && !required) || inRange(next)) onChange(next);
  };
  const [year, monthNumber] = month.split("-").map(Number);
  const firstDay = new Date(`${month}-01T12:00:00Z`).getUTCDay();
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthLength = [
    31,
    leapYear ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ][monthNumber - 1];
  const days = Array.from(
    { length: monthLength },
    (_, index) => `${month}-${String(index + 1).padStart(2, "0")}`,
  );
  const today = todayDate();

  return (
    <div
      ref={root}
      className={`date-field ${className}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          close();
        }
      }}
    >
      <div className="date-field-control">
        <input
          ref={input}
          id={inputId}
          className="date-field-input"
          type="text"
          inputMode="text"
          autoComplete="off"
          placeholder="YYYY-MM-DD"
          maxLength={10}
          value={text}
          required={required}
          disabled={disabled}
          aria-label={label}
          aria-invalid={touched && Boolean(validation)}
          aria-describedby={touched && validation ? errorId : undefined}
          onChange={(event) => updateText(event.target.value)}
          onBlur={() => setTouched(true)}
          onInvalid={() => setTouched(true)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              if (!open) toggle();
            }
            if (event.key === "Enter" && validation) {
              event.preventDefault();
              setTouched(true);
              input.current?.reportValidity();
            }
          }}
        />
        <button
          type="button"
          className="date-field-toggle"
          aria-label={`選擇${label}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          disabled={disabled}
          onClick={toggle}
        >
          <CalendarBlankIcon size={17} />
        </button>
      </div>
      {touched && validation && (
        <span id={errorId} className="date-field-error" role="alert">
          {validation}
        </span>
      )}
      {open && (
        <div
          ref={panel}
          id={panelId}
          className="date-field-panel"
          role="dialog"
          aria-label={`${label}月曆`}
          style={{ top: position.top, left: position.left }}
          onBlur={(event) => {
            if (!root.current?.contains(event.relatedTarget as Node))
              setOpen(false);
          }}
        >
          <div className="date-field-header">
            <span>{label}</span>
            <button
              type="button"
              className="date-field-close"
              onClick={close}
              aria-label="關閉月曆"
            >
              <XIcon size={16} />
            </button>
          </div>
          <div className="date-field-month">
            <button
              type="button"
              aria-label="上一個月"
              disabled={
                month <= "0001-01" || Boolean(min && month <= monthOf(min))
              }
              onClick={() => setMonth(shiftMonth(month, -1))}
            >
              <CaretLeftIcon size={17} />
            </button>
            <strong aria-live="polite">
              {year} 年 {monthNumber} 月
            </strong>
            <button
              type="button"
              aria-label="下一個月"
              disabled={
                month >= "9999-12" || Boolean(max && month >= monthOf(max))
              }
              onClick={() => setMonth(shiftMonth(month, 1))}
            >
              <CaretRightIcon size={17} />
            </button>
          </div>
          <div className="date-field-weekdays" aria-hidden="true">
            {["日", "一", "二", "三", "四", "五", "六"].map((day) => (
              <span key={day}>{day}</span>
            ))}
          </div>
          <div className="date-field-days">
            {Array.from({ length: firstDay }, (_, i) => (
              <span key={`blank-${i}`} aria-hidden="true" />
            ))}
            {days.map((date) => (
              <button
                type="button"
                key={date}
                data-date={date}
                aria-label={`${year}年${monthNumber}月${Number(date.slice(8))}日`}
                aria-pressed={date === value}
                aria-current={date === today ? "date" : undefined}
                className={`${date === value ? "date-field-selected" : ""} ${date === today ? "date-field-today" : ""}`}
                disabled={!inRange(date)}
                onClick={() => choose(date)}
                onKeyDown={(event) => {
                  const direction: Record<string, number> = {
                    ArrowLeft: -1,
                    ArrowRight: 1,
                    ArrowUp: -7,
                    ArrowDown: 7,
                  };
                  if (!(event.key in direction)) return;
                  event.preventDefault();
                  const next = new Date(`${date}T12:00:00Z`);
                  next.setUTCDate(next.getUTCDate() + direction[event.key]);
                  const nextDate = next.toISOString().slice(0, 10);
                  if (!inRange(nextDate)) return;
                  if (monthOf(nextDate) !== month) {
                    focusDate.current = nextDate;
                    setMonth(monthOf(nextDate));
                  } else
                    panel.current
                      ?.querySelector<HTMLButtonElement>(
                        `button[data-date="${nextDate}"]`,
                      )
                      ?.focus();
                }}
              >
                {Number(date.slice(8))}
              </button>
            ))}
          </div>
          <div className="date-field-footer">
            <button type="button" onClick={() => choose("")}>
              清空日期
            </button>
            <button
              type="button"
              disabled={!inRange(today)}
              onClick={() => choose(today)}
            >
              選擇今天
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
