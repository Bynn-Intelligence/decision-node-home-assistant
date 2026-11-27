# Changelog

## 0.2.0

- **Knowledge**: the decide action, standing questions and the Frigate trigger take a
  `knowledge` setting that names a knowledge base by its id, with `scope`, `top_k`,
  `require` and the other knowledge options. A decision applies the passages that fit, and
  cites them: the action's response and the event `decisionnode_decision` carry
  `evidence.knowledge` as the API sends it, and the standing question sensors and
  **Last Frigate decision** show `knowledge_status` and `knowledge_passages`.

## 0.1.0

The first release.

- A **decide** action (`decisionnode.decide`) that asks questions about a camera's picture,
  an image or a state and returns the answers, as an action response and as the event
  `decisionnode_decision`.
- **Standing questions**: a question asked on a schedule about a camera, shown as a binary
  sensor (yes or no) or a sensor (a choice, a score or a number).
- A **Frigate trigger**: a person or car detection asks your questions about that event's
  snapshot.
