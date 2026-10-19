import js from '@eslint/js'
import ts from 'typescript-eslint'
import hooks from 'eslint-plugin-react-hooks'
import refresh from 'eslint-plugin-react-refresh'

export default ts.config(
  { ignores: ['node_modules/**', 'coverage/**'] },
  js.configs.recommended,
  ...ts.configs.recommended,
  {
    files: ['**/*.ts', '**/*.tsx'],
    // TypeScript checks global names, including DOM and test APIs.
    rules: { 'no-undef': 'off' },
  },
  {
    files: ['src/**/*.tsx', 'src/**/*.ts'],
    plugins: { 'react-hooks': hooks, 'react-refresh': refresh },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
      'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
    },
  },
  {
    // Upstream shadcn variants intentionally share a file with their components.
    files: ['src/components/ui/**', 'src/test/**', 'src/**/*.test.tsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  { files: ['scripts/*.mjs'], languageOptions: { globals: { console: 'readonly', process: 'readonly', Buffer: 'readonly' } } },
  {
    files: ['scripts/*.cjs'],
    languageOptions: { globals: { require: 'readonly', __dirname: 'readonly', console: 'readonly', process: 'readonly', URL: 'readonly', window: 'readonly', document: 'readonly', getComputedStyle: 'readonly' } },
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
)
