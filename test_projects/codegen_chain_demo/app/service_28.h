#pragma once
#include <functional>
#include <vector>

class Service28 {
public:
    Service28();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
