import { apiFetch } from "./client";
import type { NotificationSettings, NotificationTestResult } from "../types";

export function getNotificationSettings(): Promise<NotificationSettings> {
  return apiFetch<NotificationSettings>("/notifications");
}

export function updateNotificationSettings(
  webhookUrl: string | null,
): Promise<NotificationSettings> {
  return apiFetch<NotificationSettings>("/notifications", {
    method: "PUT",
    body: JSON.stringify({ webhook_url: webhookUrl }),
  });
}

export function sendTestNotification(): Promise<NotificationTestResult> {
  return apiFetch<NotificationTestResult>("/notifications/test", {
    method: "POST",
  });
}
