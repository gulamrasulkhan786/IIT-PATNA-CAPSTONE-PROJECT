import axios from "axios";

const api = axios.create({
  const BASE_URL =
  process.env.REACT_APP_API_URL || "https://awarness-data-anylasis.onrender.com";

const api = axios.create({
  baseURL: BASE_URL,
});

export default api;
