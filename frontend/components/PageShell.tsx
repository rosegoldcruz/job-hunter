"use client";
import { useState } from "react";
import Topbar from "./Topbar";

interface Props {
  page: string;
  children: (search: string) => React.ReactNode;
}

export default function PageShell({ page, children }: Props) {
  const [search, setSearch] = useState("");

  return (
    <>
      <Topbar page={page} search={search} onSearch={setSearch} />
      <main className="main-content">{children(search)}</main>
    </>
  );
}
