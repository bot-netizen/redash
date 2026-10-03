import { filter, find, toString } from "lodash";
import { useState, useMemo, useEffect } from "react";
import DataSource from "@/services/data-source";

export default function useQueryDataSources(query, streamsOnly = false) {
  const [allDataSources, setAllDataSources] = useState([]);
  const [dataSourcesLoaded, setDataSourcesLoaded] = useState(false);
  const dataSources = useMemo(
    /*
      The two editors offer each other's leftovers.

      The ordinary one does not offer Kafka clusters: a window exists only
      while somebody is watching, so a saved query over one would run against
      whatever happened to be there, and a dashboard widget would be empty most
      of the time. The stream editor offers nothing else, because everything
      else has no window to watch.

      Either way the one already chosen stays in the list, so an existing query
      never silently loses its data source.
    */
    () =>
      filter(
        allDataSources,
        (ds) => (!ds.view_only && !!ds.streams_only === !!streamsOnly) || ds.id === query.data_source_id
      ),
    [allDataSources, query.data_source_id, streamsOnly]
  );
  const dataSource = useMemo(
    () => find(dataSources, (ds) => toString(ds.id) === toString(query.data_source_id)) || null,
    [query.data_source_id, dataSources]
  );

  useEffect(() => {
    let cancelDataSourceLoading = false;
    DataSource.query().then((data) => {
      if (!cancelDataSourceLoading) {
        setDataSourcesLoaded(true);
        setAllDataSources(data);
      }
    });

    return () => {
      cancelDataSourceLoading = true;
    };
  }, []);

  return useMemo(() => ({ dataSourcesLoaded, dataSources, dataSource }), [dataSourcesLoaded, dataSources, dataSource]);
}
