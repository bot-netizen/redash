import { isEmpty } from "lodash";
import { useCallback, useState, useMemo } from "react";
import useUpdateQuery from "./useUpdateQuery";
import navigateTo from "@/components/ApplicationArea/navigateTo";

export default function useQuery(originalQuery) {
  const [query, setQuery] = useState(originalQuery);
  const [originalQuerySource, setOriginalQuerySource] = useState(originalQuery.query);
  const [originalAutoLimit, setOriginalAutoLimit] = useState(query.options.apply_auto_limit);

  /*
    The query as the server now holds it, rather than as somebody is editing it.

    `isDirty` is the editor's SQL measured against a baseline, and until now the
    only thing that moved that baseline was saving. Anything else that changes
    the SQL from outside the editor -- restoring a version is the first --
    leaves the editor claiming unsaved changes for text the server already has,
    and warning on the way out about losing it.
  */
  const markSaved = useCallback((updatedQuery) => {
    setQuery(updatedQuery);
    setOriginalQuerySource(updatedQuery.query);
    setOriginalAutoLimit(updatedQuery.options.apply_auto_limit);
  }, []);

  const updateQuery = useUpdateQuery(query, (updatedQuery) => {
    // It's important to update URL first, and only then update state
    if (updatedQuery.id !== query.id) {
      // Don't reload page when saving new query
      navigateTo(updatedQuery.getUrl(true), true);
    }
    markSaved(updatedQuery);
  });

  return useMemo(
    () => ({
      query,
      setQuery,
      markSaved,
      isDirty:
        query.query !== originalQuerySource ||
        (!isEmpty(query.query) && query.options.apply_auto_limit !== originalAutoLimit),
      saveQuery: () => updateQuery(),
    }),
    [query, originalQuerySource, updateQuery, originalAutoLimit, markSaved]
  );
}
