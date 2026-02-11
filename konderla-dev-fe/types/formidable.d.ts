declare module 'formidable' {
  interface Options {
    maxFileSize?: number;
    keepExtensions?: boolean;
    [key: string]: unknown;
  }
  interface File {
    filepath: string;
    originalFilename: string;
    mimetype?: string;
    size: number;
  }
  interface Fields {
    [key: string]: string | string[] | undefined;
  }
  interface Files {
    [key: string]: File | File[] | undefined;
  }
  function formidable(options?: Options): {
    parse: (req: unknown) => Promise<[Fields, Files]>;
  };
  export = formidable;
}
