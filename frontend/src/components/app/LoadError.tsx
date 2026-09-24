import type { ApiError } from '../../api';
import { withObjectParticle } from '../../lib/format';
import { Alert, Button } from '../ui';

/** Standard "couldn't load" message with a retry button. */
export function LoadError({ error, onRetry, what = '정보' }: { error: ApiError; onRetry?: () => void; what?: string }) {
  return (
    <Alert
      tone="danger"
      title={`${withObjectParticle(what)} 불러오지 못했어요`}
      action={
        onRetry && (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            다시 불러오기
          </Button>
        )
      }
    >
      {error.message}
    </Alert>
  );
}
