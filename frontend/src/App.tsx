import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import AmbientSonics from "./AmbientSonics";
import Db from "./pages/Db";
import OptPrm from "./pages/OptPrm";
import Optimized from "./pages/Optimized";
import Notification from "./pages/Notification";
import Parsing from "./pages/Parsing";
import Search from "./pages/Search";
import Sell from "./pages/Sell";

export default function App() {
  return (
    <div className="app-shell">
      <AmbientSonics />
      <nav className="top-nav">
        <NavLink
          to="/parsing"
          className={({ isActive }) => (isActive ? "active" : "")}
          end
        >
          Парс
        </NavLink>
        <NavLink
          to="/search"
          className={({ isActive }) => (isActive ? "active" : "")}
        >
          Поиск
        </NavLink>
        <NavLink
          to="/db"
          className={({ isActive }) => (isActive ? "active" : "")}
          end
        >
          БД
        </NavLink>
        <NavLink
          to="/optimized"
          className={({ isActive }) => (isActive ? "active" : "")}
          end
        >
          Opt
        </NavLink>
        <NavLink
          to="/optprm"
          className={({ isActive }) => (isActive ? "active" : "")}
          end
        >
          OptPrm
        </NavLink>
        <NavLink
          to="/sell"
          className={({ isActive }) => (isActive ? "active" : "")}
          end
        >
          Sell
        </NavLink>
        <NavLink
          to="/notification"
          className={({ isActive }) => (isActive ? "active" : "")}
          end
        >
          Notify
        </NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Navigate to="/parsing" replace />} />
        <Route path="/parsing" element={<Parsing />} />
        <Route path="/search" element={<Search />} />
        <Route path="/db" element={<Db />} />
        <Route path="/optimized" element={<Optimized />} />
        <Route path="/optprm" element={<OptPrm />} />
        <Route path="/optimized2" element={<Navigate to="/optimized" replace />} />
        <Route path="/sell" element={<Sell />} />
        <Route path="/notification" element={<Notification />} />
      </Routes>
    </div>
  );
}
