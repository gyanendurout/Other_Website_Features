import { READONLY } from "@/lib/db";
import CaptureForm from "./capture-form";

export const dynamic = "force-dynamic";

export default function Capture() {
  return (
    <div className="section" style={{ paddingTop: 40 }}>
      <CaptureForm readOnly={READONLY} />
    </div>
  );
}
