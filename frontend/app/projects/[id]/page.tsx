"use client";

import { use } from "react";
import Workspace from "@/components/Workspace";
import Shell from "@/components/Shell";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Shell>
      <Workspace projectId={id} />
    </Shell>
  );
}
