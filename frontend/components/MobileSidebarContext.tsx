"use client";
import { createContext, useContext } from "react";

interface MobileNavCtx {
  isOpen: boolean;
  toggle: () => void;
  close: () => void;
}

export const MobileNavContext = createContext<MobileNavCtx>({
  isOpen: false,
  toggle: () => {},
  close: () => {},
});

export const useMobileNav = () => useContext(MobileNavContext);
