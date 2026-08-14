const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");
const {
  BitableAppWebpackPlugin,
  opdevMiddleware,
} = require("@lark-opdev/block-bitable-webpack-utils");

module.exports = (_env, argv) => {
  process.env.NODE_ENV = argv.mode;
  return {
    entry: "./src/index.tsx",
    output: {
      path: path.resolve(__dirname, "dist"),
      filename: "app.[contenthash].js",
      clean: true,
    },
    resolve: { extensions: [".tsx", ".ts", ".js"] },
    module: {
      rules: [
        { test: /\.tsx?$/, use: "ts-loader", exclude: /node_modules/ },
        { test: /\.css$/, use: ["style-loader", "css-loader"] },
      ],
    },
    plugins: [
      new HtmlWebpackPlugin({ template: "./src/index.html" }),
      new BitableAppWebpackPlugin({ open: false }),
    ],
    devServer: {
      host: "127.0.0.1",
      port: 3001,
      hot: true,
      allowedHosts: "all",
      setupMiddlewares: (middlewares, devServer) => {
        middlewares.push(opdevMiddleware(devServer));
        return middlewares;
      },
    },
  };
};
