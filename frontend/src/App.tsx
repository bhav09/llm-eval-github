import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import EvalPage from "@/pages/EvalPage";
import { ModelSelectionPage } from "@/pages/ModelSelectionPage";
import { RunHistoryPage } from "@/pages/RunHistoryPage";
import { AboutPage } from "@/pages/AboutPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/selection" replace />} />
          <Route path="/selection" element={<ModelSelectionPage />} />
          <Route path="/eval" element={<EvalPage />} />
          <Route path="/history" element={<RunHistoryPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/selection" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
