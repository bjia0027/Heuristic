#pragma once
#include <functional>
#include <vector>

class Service30 {
public:
    Service30();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
