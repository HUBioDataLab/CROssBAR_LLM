import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import AgentToggleList from './AgentToggleList';

const catalog = [
  { id: 'knowledge_graph', name: 'Knowledge Graph', summary: 'Graph data', available: true },
  { id: 'paperclip', name: 'Paperclip', summary: 'Paper search', available: true },
  { id: 'pubtator3', name: 'PubTator3', summary: 'Literature search', available: true },
];

const allEnabled = {
  knowledge_graph: true,
  paperclip: true,
  pubtator3: true,
};

test('explains that every selected agent runs', () => {
  render(
    <AgentToggleList catalog={catalog} enabled={allEnabled} onChange={jest.fn()} />,
  );

  expect(screen.getByText(/Every selected agent runs/i)).toBeTruthy();
});

test('vector mode locks KG on and literature agents off without changing saved choices', () => {
  const onChange = jest.fn();
  render(
    <AgentToggleList
      catalog={catalog}
      enabled={allEnabled}
      onChange={onChange}
      lockedOn={['knowledge_graph']}
      lockedOff={['paperclip', 'pubtator3']}
    />,
  );

  const kg = screen.getByRole('checkbox', { name: /Enable the Knowledge Graph agent/i });
  const paperclip = screen.getByRole('checkbox', { name: /Enable the Paperclip agent/i });
  const pubtator3 = screen.getByRole('checkbox', { name: /Enable the PubTator3 agent/i });

  expect(kg.checked).toBe(true);
  expect(paperclip.checked).toBe(false);
  expect(pubtator3.checked).toBe(false);
  expect(kg.disabled).toBe(true);
  expect(paperclip.disabled).toBe(true);
  expect(pubtator3.disabled).toBe(true);

  fireEvent.click(paperclip);
  expect(onChange).not.toHaveBeenCalled();
  expect(allEnabled).toEqual({
    knowledge_graph: true,
    paperclip: true,
    pubtator3: true,
  });
});
