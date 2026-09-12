import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./components/Dashboard";
import Editor from "./components/Editor";
import ClipPicker from "./components/ClipPicker";
import "./styles/globals.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/pick/:projectId" element={<ClipPicker />} />
        <Route path="/editor/:projectId" element={<Editor />} />
      </Routes>
    </BrowserRouter>
  );
}
