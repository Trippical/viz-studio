import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchTree } from '../api/client';
import type { Tree, TreeFolder, TreeItem } from '../api/types';
import { ErrorCard } from '../components/ErrorCard';
import { Markdown } from '../components/Markdown';

type Kind = 'charts' | 'dashboards';

function itemHref(kind: Kind, item: TreeItem): string {
  return kind === 'charts' ? `/c/${item.id}` : `/d/${item.id}`;
}

function Item({ kind, item }: { kind: Kind; item: TreeItem }) {
  if (item.error) {
    return (
      <span className="item-error">
        {item.id}: {item.error}
      </span>
    );
  }
  return (
    <>
      <Link to={itemHref(kind, item)}>{item.title ?? item.id}</Link>
      {item.type === 'chart' && item.static && <span className="badge">static</span>}
    </>
  );
}

function Folder({ kind, folder, root }: { kind: Kind; folder: TreeFolder; root: boolean }) {
  return (
    <div>
      {!root && (
        <div className="folder-title">
          {folder.title ?? folder.name}
          {folder.error && <span className="item-error"> ({folder.error})</span>}
        </div>
      )}
      {!root && folder.description && <Markdown text={folder.description} />}
      <ul>
        {folder.items.map((item) => (
          <li key={item.id}>
            <Item kind={kind} item={item} />
          </li>
        ))}
        {folder.folders.map((child) => (
          <li key={child.path}>
            <Folder kind={kind} folder={child} root={false} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TreePage({ kind }: { kind: Kind }) {
  const [tree, setTree] = useState<Tree | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setTree(null);
    setError(null);
    fetchTree()
      .then((t) => {
        if (!cancelled) setTree(t);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [kind]);

  return (
    <div className="tree">
      <h2>{kind === 'charts' ? 'Charts' : 'Dashboards'}</h2>
      {error && <ErrorCard id={kind} reason={error} />}
      {!error && !tree && <div className="muted">Loading…</div>}
      {tree && <Folder kind={kind} folder={tree[kind]} root />}
    </div>
  );
}
