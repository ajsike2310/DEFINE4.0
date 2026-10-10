import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./styles/index.css";
import AppLayout from "./layouts/AppLayout";
import { EventProvider } from "./hooks/useEvent";
import { NotifyProvider } from "./hooks/useNotify";

// Route-level code splitting: charts (recharts) only load for Dashboard/Analytics.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Campaigns = lazy(() => import("./pages/Campaigns"));
const NewCampaign = lazy(() => import("./pages/NewCampaign"));
const CampaignDetail = lazy(() => import("./pages/CampaignDetail"));
const ParticipantsPage = lazy(() => import("./pages/Participants"));
const FollowUpQueue = lazy(() => import("./pages/FollowUpQueue"));
const EventsPage = lazy(() => import("./pages/EventsPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const LeadsPage = lazy(() => import("./pages/LeadsPage"));
const JoinPage = lazy(() => import("./pages/JoinPage"));

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <NotifyProvider><EventProvider>
        <Suspense fallback={null}><Routes>
          <Route path="join/:eventId" element={<JoinPage />} />
          <Route element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="campaigns" element={<Campaigns />} />
            <Route path="campaigns/new" element={<NewCampaign />} />
            <Route path="campaigns/:id" element={<CampaignDetail />} />
            <Route path="leads" element={<LeadsPage />} />
            <Route path="participants" element={<ParticipantsPage />} />
            <Route path="followups" element={<FollowUpQueue />} />
            <Route path="events" element={<EventsPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes></Suspense>
      </EventProvider></NotifyProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
