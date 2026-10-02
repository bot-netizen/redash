import { filter, find, toString } from "lodash";
import { useState, useMemo, useEffect } from "react";
import DataSource from "@/services/data-source";

export default function useQueryDataSources(query) {
  const [allDataSources, setAllDataSources] = useState([]);
  const [dataSourcesLoaded, setDataSourcesLoaded] = useState(false);
  const dataSources = useMemo(
    // A Kafka cluster is not offered here. Its tables exist only while
    // somebody is watching, so a saved query against one would run against
    // whatever happened to be in the window at the time; streams have their
    // own tab. One already chosen stays in the list, so an existing query does
    // not silently lose its data source.
    () =>
      filter(
        allDataSources,
        (ds) => (!ds.view_only && !ds.streams_only) || ds.id === query.data_source_id
      ),
    [allDataSources, query.data_source_id]
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
