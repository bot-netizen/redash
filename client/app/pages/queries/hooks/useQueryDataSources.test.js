import React from "react";
import { mount } from "enzyme";

import useQueryDataSources from "./useQueryDataSources";
import DataSource from "@/services/data-source";

/*
  The two editors offer each other's leftovers.

  The ordinary one does not offer Kafka clusters: a window exists only while
  somebody is watching, so a saved query over one would run against whatever
  happened to be there. The stream editor offers nothing else, because
  everything else has no window to watch.
*/
function Probe({ query, streamsOnly }) {
  const { dataSources } = useQueryDataSources(query, streamsOnly);
  return <span className="names">{dataSources.map((ds) => ds.name).join(",")}</span>;
}

const SOURCES = [
  { id: 1, name: "Warehouse", view_only: false, streams_only: false },
  { id: 2, name: "Kafka", view_only: false, streams_only: true },
  { id: 3, name: "ReadOnly", view_only: true, streams_only: false },
];

async function names(streamsOnly, dataSourceId = 1) {
  jest.spyOn(DataSource, "query").mockResolvedValue(SOURCES);
  const wrapper = mount(<Probe query={{ data_source_id: dataSourceId }} streamsOnly={streamsOnly} />);
  for (let index = 0; index < 3; index += 1) {
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 0));
    wrapper.update();
  }
  return wrapper.find(".names").text();
}

describe("useQueryDataSources", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("the ordinary editor leaves clusters out", async () => {
    expect(await names(false)).toBe("Warehouse");
  });

  test("the stream editor offers only clusters", async () => {
    expect(await names(true, 2)).toBe("Kafka");
  });

  test("a view-only source is left out of both", async () => {
    expect(await names(false)).not.toContain("ReadOnly");
    expect(await names(true, 2)).not.toContain("ReadOnly");
  });

  test("the one already chosen stays, whichever editor it is", async () => {
    // So an existing query never silently loses its data source -- including
    // a stream query opened in the ordinary editor by an old link.
    expect(await names(false, 2)).toContain("Kafka");
  });
});
