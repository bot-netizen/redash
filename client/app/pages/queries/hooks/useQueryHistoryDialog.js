import { useCallback } from "react";
import QueryHistoryDialog from "@/components/queries/QueryHistoryDialog";
import useImmutableCallback from "@/lib/hooks/useImmutableCallback";

export default function useQueryHistoryDialog(query, canRestore, onChange) {
  const handleChange = useImmutableCallback(onChange);

  return useCallback(() => {
    QueryHistoryDialog.showModal({ query, canRestore }).onClose(handleChange);
  }, [query, canRestore, handleChange]);
}
